"""xlsx_edit.py - THE single primitive for modifying an .xlsx, surgically.

openpyxl is unusable for our edits: a `load_workbook` -> `save` round-trip FLATTENS dynamic-array /
spill formulas (it keeps the array master AND emits literal "slave" cells inside the same range, which
Excel rejects as an "overlapping array formula" / corrupt file) and drops formula caches. This module
instead edits ONLY the worksheet parts that change, INSIDE the original zip, and copies every other
part BYTE-FOR-BYTE - so shared/array formulas, formula caches, tables and styles in untouched parts
survive because they are never touched. Cell edits are a regex rewrite of the existing `<c>` element
(the approach the corruption diagnosis verified produces valid XML). The ARRAY GUARD strips an array
master whose range an edit writes into, so the app can OWN a column (e.g. phase 200's Suggested Type)
with no master+literal overlap left behind.

This is meant to be the ONE place that writes an .xlsx (folding in the old io/xlsx_cache formula-cache
restore and, later, the interface-sheet/table insertion from domain/interfaces). `set_cells` is the
pure per-sheet engine; `edit_workbook` is the zip-level orchestrator (atomic temp + os.replace).
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
    as an inline string, preserving the cell's existing style; cells/rows that don't exist are inserted
    in order."""
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
        new_cell = f'<c r="{ref}"{(" s=" + chr(34) + _style_of(existing.group(0)) + chr(34)) if existing and _style_of(existing.group(0)) else ""} t="inlineStr"><is><t xml:space="preserve">{_esc(value)}</t></is></c>'
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


def edit_workbook(path: str, *, cell_edits: dict | None = None, dest: str | None = None) -> list:
    """THE primitive: apply `cell_edits` = {sheet_name: {cell_ref: value}} to `path`, editing ONLY the
    affected worksheet parts and byte-copying every other part. Atomic (temp + os.replace); `dest`
    defaults to `path` (in-place). Returns a list of (sheet_name, master_ref, range) for any array
    formulas FROZEN to their cached values to make room for an edit (the caller logs these as
    warnings); [] when nothing was written. new_sheets support (DiagnosisBlocks / _UnresolvedIndex /
    interface sheets) is added next."""
    cell_edits = cell_edits or {}
    if not cell_edits:
        return []
    dest = dest or path
    with open(path, "rb") as f:
        data = f.read()
    parts = _sheet_name_to_part(data)
    repl = {}
    materialized = []
    for sheet_name, edits in cell_edits.items():
        part = parts.get(sheet_name)
        if not part or not edits:
            continue
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            xml = z.read(part).decode("utf-8")
        new_xml, mats = set_cells(xml, edits)
        repl[part] = new_xml.encode("utf-8")
        materialized += [(sheet_name, m, r) for (m, r) in mats]
    if not repl:
        return []
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as zin, \
            zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for it in zin.infolist():
            zout.writestr(it, repl.get(it.filename) or zin.read(it.filename))
    tmp = dest + ".tmp_edit"
    with open(tmp, "wb") as f:
        f.write(out.getvalue())
    os.replace(tmp, dest)
    return materialized
