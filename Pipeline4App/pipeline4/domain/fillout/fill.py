"""ph200 sub-phase 210 - the in-place fill of the source I/O List's Script Type (AB) + Suggested Type (AC).

Clean-room port of PL3's `populate` for the script-type leg, doc-only (ph200 does NOT write the SSOT;
staging reads the now-filled doc). Per row: compute the script_type from the CSV rules (`classify`); write
AC always (the app-owned reference column), write AB only when it's blank/`<input required>` (Mode-1) and
PRESERVE a genuine human AB value (Mode-2, audited as a WARN when it diverges). The write is SURGICAL
(`io/xlsx_edit`): only the edited cells + the rebuilt `_UnresolvedIndex` sheet change, everything else is
byte-copied; a timestamped backup is taken first and DELETED when the fill changed nothing (compared by
cell VALUES). A row left `<input required>` (and not skipped) is a blocking `fill_unresolved` finding.
"""
from __future__ import annotations

import os
import shutil
from collections import defaultdict
from datetime import datetime

from openpyxl import load_workbook
from openpyxl.utils import column_index_from_string as _ci

from pipeline4.core import config
from pipeline4.core.expr import runtime as _expr_runtime
from pipeline4.core.finding import Finding
from pipeline4.domain.fillout import (
    classify, reader, diag_blocks, index_assign, diag_alloc,
)
from pipeline4.domain.fillout.families import load_object_families
from pipeline4.io import xlsx_edit

INPUT_REQUIRED = classify.INPUT_REQUIRED
_clean = _expr_runtime.clean              # the shared text cleaner (control chars -> space, ws collapse)
_UNRESOLVED_SHEET = "_UnresolvedIndex"
# the pipeline-owned output columns whose HEADER is written (only into a blank header cell - a customized
# header is preserved) - mirrors PL3's HEADER_COLS.
_OUTPUT_COLS = ("skip_reason", "script_type", "suggested_type", "index",
                "diag_cabinet", "diag_bit", "hardware_params")


def _f(type_: str, severity: str, detail: str, location: str = "") -> Finding:
    return Finding(phase=200, type=type_, severity=severity, detail=detail, location=location)


def _blank(value) -> bool:
    s = str(value or "").strip()
    return s == "" or s == INPUT_REQUIRED


def _skipped(raw: dict) -> bool:
    """A row the fill leaves alone for halting purposes (mirrors PL3's skip reasons, minus strike for now):
    a struck-out mnemonic `-`, or a non-empty Skip Reason cell."""
    if str(raw.get("mnemonic") or "").strip() == "-":
        return True
    return str(raw.get("skip_reason") or "").strip() not in ("", "0", "0.0")


def _backup_path(src: str) -> str:
    base, ext = os.path.splitext(src)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path, i = f"{base}.bak_{stamp}{ext}", 1
    while os.path.exists(path):
        path = f"{base}.bak_{stamp}_{i}{ext}"
        i += 1
    return path


def _same_content(a: str, b: str) -> bool:
    """True when two workbooks are VALUE-identical (sheet names + per-sheet dims + every cell value). A
    surgical re-write perturbs the bytes but not the values, so an idempotent re-fill compares equal and
    the backup is removed (PL3's `_same_content`)."""
    wa = load_workbook(a, data_only=True, read_only=True)
    wb = load_workbook(b, data_only=True, read_only=True)
    try:
        if wa.sheetnames != wb.sheetnames:
            return False
        for name in wa.sheetnames:
            sa, sb = wa[name], wb[name]
            if (sa.max_row, sa.max_column) != (sb.max_row, sb.max_column):
                return False
            for ra, rb in zip(sa.iter_rows(values_only=True), sb.iter_rows(values_only=True)):
                if list(ra) != list(rb):
                    return False
        return True
    finally:
        wa.close()
        wb.close()


def _read_output_headers(io_path: str, sheets: list, colmap: list, header_row: int) -> dict:
    """{sheet -> {canonical -> header cell value}} for the output columns, to decide which headers are blank."""
    letters = {m["canonical"]: m["column"] for m in colmap}
    wb = load_workbook(io_path, data_only=True)
    try:
        out = {}
        for sheet in sheets:
            if sheet not in wb.sheetnames:
                continue
            ws = wb[sheet]
            out[sheet] = {c: ws.cell(header_row, _ci(letters[c])).value
                          for c in _OUTPUT_COLS if c in letters}
        return out
    finally:
        wb.close()


def _unresolved_sheet(unresolved: list, ab_col: str) -> dict:
    """The `_UnresolvedIndex` sheet spec: a header + one row per unresolved signal, col A an internal
    hyperlink to the exact AB cell to fix."""
    rows = [["Source", "Script Type", "Device (FLD)", "Description", "Reason"]]
    links = []
    for i, raw in enumerate(unresolved, start=2):
        sheet, rownum = raw["source_sheet"], raw["source_row"]
        fld = (str(raw.get("functional_unit") or "") + str(raw.get("location") or "")
               + str(raw.get("device") or "")).strip()
        desc = (_clean(raw.get("desc_l1")) + " " + _clean(raw.get("desc_l1b"))).strip()
        rows.append([f"{sheet} - Row {rownum}", "", fld, desc, "unmatched type"])
        links.append((f"A{i}", f"'{sheet}'!{ab_col}{rownum}", f"{sheet} - Row {rownum}"))
    return {"name": _UNRESOLVED_SHEET, "rows": rows, "hyperlinks": links}


def fill_script_type(params: dict | None = None) -> dict:
    """Fill AB/AC in the source I/O List in place (the 210-only leg). Kept for call-site compatibility -
    delegates to the integrated `fill_out(only=210)`. Returns the same shape as before
    ({output_path, backup, findings, filled, mismatch, unresolved})."""
    return fill_out(params, only=210)


# --------------------------------------------------------------------------------------------- #
# the INTEGRATED ph200 fill: 210 (script_type/suggested) + 220 (index) + 230/240 (diag) in one
# write-back to the source I/O List, then staging re-reads the now-filled doc (doc-only; the SSOT is
# the re-stage). NON-DESTRUCTIVE: a timestamped backup is taken before the surgical write and dropped
# when the fill changed nothing (value-identical no-op).
# --------------------------------------------------------------------------------------------- #
def _compute_fill(params: dict, only) -> tuple:
    """The COMPUTATION half (no I/O write): stage the source, run 210/220/230/240 over the staged rows
    (each leg re-resolving the type so the next leg sees it), and return
    (rows, blocks, place, gate_rules, type_rules) where `rows` carry the computed script_type/suggested/
    index/diag_cabinet/diag_bit fields and `blocks` is the ordered DiagBlock list (the DiagnosisBlocks
    write-back). `only` restricts the WRITE-BACK leg (each leg still computes its prerequisites)."""
    from pipeline4.domain import staging

    gate_rules, type_rules = config.load_gate_rules(), config.load_script_type_rules()
    families = load_object_families()
    # merge the per-type diagnosis attrs onto each type record BEFORE re-resolving (mirrors staging's
    # _read_iolist) so the re-resolved `type` carries in_diag/diag_logic/tristate - 230/240 read in_diag.
    signal_types = config.load_signal_types()
    signal_diag = config.load_signal_diagnosis()
    for t in signal_types.values():
        d = signal_diag.get(t["type_id"].upper(), {})
        t["in_diag"] = d.get("in_diag", False)
        t["diag_logic"] = d.get("diag_logic", "")
        t["tristate"] = d.get("tristate", False)
        t["tristate_desc"] = d.get("tristate_desc", "")

    db, _ = staging.stage(params)                                   # stage #1 - the read of the source doc
    rows = list(db.table("signals"))

    # stash each row's ORIGINAL (as-read) write-back cells BEFORE the legs overwrite them - the surgical
    # write-back is non-destructive (Mode-1 blank-only) and the derived DiagnosisBlocks columns read the
    # real on-disk (cabinet, bit), so it must compare against the pre-fill values, not the computed ones.
    for row in rows:
        for canon in ("script_type", "index", "diag_cabinet", "diag_bit"):
            row[f"_orig_{canon}"] = row.get(canon, "")

    # 210 - classify: set script_type (Mode-1 only when AB is blank/<input required>; Mode-2 preserves a
    # human AB + a fill_type_mismatch WARN) and the always-on suggested = computed; RE-RESOLVE the type so
    # 220/230/240 see it.
    findings, mismatch = [], 0
    for row in rows:
        computed = classify.classify(row, gate_rules, type_rules)
        row["suggested_computed"] = computed                        # AC: always the computed value
        ex_ab = str(row.get("script_type") or "").strip()
        if ex_ab and ex_ab != INPUT_REQUIRED:                       # Mode-2: keep the human value
            if computed and computed not in (ex_ab, INPUT_REQUIRED):
                mismatch += 1
                findings.append(_f("fill_type_mismatch", "WARN",
                                   f"kept the existing script type {ex_ab!r}; the rules computed {computed!r}",
                                   f"{row.get('source_sheet')}!{row.get('source_row')}"))
        elif computed:                                              # Mode-1: take the computed value
            row["script_type"] = computed
        row["type"] = config.resolve_type(signal_types, row.get("script_type"))

    # 220 - index assignment over the (re-typed) rows.
    idx = index_assign.assign_indices(rows, families)
    for row in rows:
        row["index"] = idx.get(row["uid"], row.get("index", ""))

    # 230/240 - diagnosis allocation. `existing` = {full_name -> cabinet_id} from the staged
    # diagnosis_cabinets table (stable-id idempotency); `place` = {uid -> (diag_cabinet, diag_bit)}.
    existing = {c["fld"]: int(c["cabinet_id"]) for c in db.table("diagnosis_cabinets")
                if str(c.get("fld") or "").strip()}
    blocks, place = diag_alloc.allocate(rows, families, params, existing)
    for row in rows:
        cab, bit = place.get(row["uid"], ("", ""))
        row["diag_cabinet"], row["diag_bit"] = cab, bit

    return rows, blocks, place, findings, mismatch


def _legs(only) -> set:
    """The set of sub-phases whose WRITE-BACK runs. `only` in {210,220,230,240} restricts to that leg
    (230/240 are paired - the diag write + the DiagnosisBlocks sheet move together); None = all four."""
    if only in (230, 240):
        return {230, 240}
    if only in (210, 220):
        return {only}
    return {210, 220, 230, 240}


def fill_out(params: dict | None = None, only=None) -> dict:
    """The integrated ph200 fill: compute 210/220/230/240 over a staging read of the source I/O List,
    then write AB(script_type)/AC(suggested)/AD(index)/AE(diag_cabinet)/AF(diag_bit) back into the doc by
    source_sheet/source_row, refresh the output-col headers + the _UnresolvedIndex sheet, and APPEND the
    new DiagnosisBlocks cabinets + refresh its derived columns. Doc-only (the SSOT is the re-stage). A
    timestamped backup is taken first and dropped on a value-identical no-op. `only` in {210,220,230,240}
    runs just that leg's write-back (still computing its prerequisites). Returns
    {output_path, backup, findings, filled, index, diag, unresolved, mismatch}."""
    params = params or config.load_params()
    io_path = params.get("iolist_path")
    if not io_path or not os.path.exists(io_path):
        return {"output_path": io_path or "", "backup": "", "filled": 0, "index": 0, "diag": 0,
                "unresolved": 0, "mismatch": 0,
                "findings": [_f("fill_no_iolist", "FAIL", f"I/O List not found: {io_path!r}", io_path or "")]}

    legs = _legs(only)
    colmap = config.load_column_map("IoList")
    header_row = int(config.get_param(params, "iolist_params.header_row", 1) or 1)
    min_b = int(config.get_param(params, "iolist_params.diag_bit_min", 0) or 0)
    max_b = int(config.get_param(params, "iolist_params.diag_bit_max", 62) or 62)

    rows, blocks, place, findings, mismatch = _compute_fill(params, only)

    def _letter(canon):
        return next((m["column"] for m in colmap if m["canonical"] == canon), None)

    def _header(canon):
        return next((m["expected_header"] for m in colmap if m["canonical"] == canon), "")

    ab, ac = _letter("script_type"), _letter("suggested_type")
    ad, ae, af = _letter("index"), _letter("diag_cabinet"), _letter("diag_bit")
    sheets = list(dict.fromkeys(r["source_sheet"] for r in rows))
    headers = _read_output_headers(io_path, sheets, colmap, header_row)

    cell_edits: dict = defaultdict(dict)
    unresolved = []
    filled = indexed = diagnosed = 0

    for sheet in sheets:                                            # the output-col headers (only if blank)
        for canon in _OUTPUT_COLS:
            col, hdr = _letter(canon), _header(canon)
            cur = headers.get(sheet, {}).get(canon)
            if col and hdr and (cur is None or str(cur).strip() == ""):
                cell_edits[sheet][f"{col}{header_row}"] = hdr

    for row in rows:
        sheet, rownum = row["source_sheet"], row["source_row"]
        # 210 - AB (Mode-1 blank-only) + AC (always the computed suggested)
        if 210 in legs:
            computed = row.get("suggested_computed") or ""
            if ac and computed:
                cell_edits[sheet][f"{ac}{rownum}"] = computed
            st = str(row.get("script_type") or "").strip()
            if ab and computed and _blank(row.get("_orig_script_type")):
                # AB was originally blank/<input required> -> Mode-1 write; a preserved human AB is left alone
                cell_edits[sheet][f"{ab}{rownum}"] = row["script_type"]
                if st and st != INPUT_REQUIRED:
                    filled += 1
            if st == INPUT_REQUIRED and not _skipped(row):
                unresolved.append(row)
                findings.append(_f("fill_unresolved", "FAIL",
                                   "the description matched no script-type rule - fill it in the source I/O List",
                                   f"{sheet}!{ab}{rownum}"))
        # 220 - AD index (blank-only)
        if 220 in legs and ad:
            ix = str(row.get("index") or "").strip()
            if ix and _blank(_orig_cell(row, "index")):
                cell_edits[sheet][f"{ad}{rownum}"] = row["index"]
                if ix != INPUT_REQUIRED:
                    indexed += 1
        # 230/240 - AE diag_cabinet + AF diag_bit (blank-only)
        if 230 in legs:
            cab = str(row.get("diag_cabinet") or "").strip()
            bit = str(row.get("diag_bit") or "").strip()
            if ae and cab and _blank(_orig_cell(row, "diag_cabinet")):
                cell_edits[sheet][f"{ae}{rownum}"] = cab
                diagnosed += 1
            if af and bit and _blank(_orig_cell(row, "diag_bit")):
                cell_edits[sheet][f"{af}{rownum}"] = bit

    new_sheets, append = [], {}
    if 230 in legs:
        _diag_blocks_write(io_path, rows, blocks, place, min_b, max_b, cell_edits, new_sheets, append)

    # the _UnresolvedIndex report sheet (only the 210 leg owns it; rebuilt fresh each run)
    if 210 in legs:
        new_sheets.append(_unresolved_sheet(unresolved, ab))

    backup = _backup_path(io_path)
    shutil.copy2(io_path, backup)
    frozen = xlsx_edit.edit_workbook(io_path, cell_edits={s: e for s, e in cell_edits.items() if e},
                                     new_sheets=new_sheets or None, append_rows=append or None)
    for sheet, master, rng in frozen:
        findings.append(_f("fill_array_frozen", "WARN",
                           f"froze a dynamic array (spill {rng}) the fill landed in", f"{sheet}!{master}"))
    if _same_content(backup, io_path):                             # value-identical no-op -> drop the backup
        os.remove(backup)
        backup = ""
    return {"output_path": io_path, "backup": backup, "findings": findings,
            "filled": filled, "index": indexed, "diag": diagnosed,
            "unresolved": len(unresolved), "mismatch": mismatch}


def _orig_cell(row: dict, canon: str) -> str:
    """The row's ORIGINAL (pre-fill) cell value for a write-back column. Staging stores the as-read cell on
    the canonical key, and 220/230/240 OVERWRITE that key with the computed value - so the pre-fill value is
    stashed under `_orig_<canon>` by the staging read. We fall back to the live value (Mode-2-style preserve)
    when no stash is present."""
    return str(row.get(f"_orig_{canon}", row.get(canon)) or "").strip()


def _diag_blocks_write(io_path, rows, blocks, place, min_b, max_b, cell_edits, new_sheets, append) -> None:
    """The DiagnosisBlocks leg of the write-back (PL3 `populate` §9, ported): read the existing sheet for
    the stable IDs + the existing rows, compute the derived columns from the REAL post-fill (Diag_Cabinet,
    Diag_Bit) of every row, then APPEND only the cabinets not already present + refresh the derived columns
    in place; create the sheet fresh when it is ABSENT."""
    wb = load_workbook(io_path, data_only=True)
    try:
        existing_ids, rows_by_cid, blk_header = diag_blocks.read_existing(wb)
        present_name = next((s for s in wb.sheetnames
                             if s.strip().lower() in (diag_blocks.DIAGBLOCKS_SHEET.lower(),
                                                      diag_blocks.DIAGBLOCKS_LEGACY.lower())), None)
    finally:
        wb.close()

    # the REAL post-fill (cabinet, bit): the original on-disk value if non-blank, else what this run writes.
    placed = []
    for row in rows:
        ex_cab = _orig_cell(row, "diag_cabinet")
        cab = diag_blocks._norm_cab(ex_cab) if ex_cab else str(row.get("diag_cabinet") or "").strip()
        if not cab:
            continue
        ex_bit = _orig_cell(row, "diag_bit")
        bit = diag_blocks._bit_int(ex_bit) if ex_bit else diag_blocks._bit_int(row.get("diag_bit"))
        placed.append((cab, bit))
    derived = diag_blocks.analyze(placed, min_b, max_b)
    default = (0, diag_blocks._fmt_ranges(range(min_b, max_b + 1)), "")

    if present_name:                                               # APPEND-ONLY identity; REFRESH derived
        cell_edits.setdefault(present_name, {}).update(
            diag_blocks.derived_edits(blk_header, rows_by_cid, derived, default))
        new = [b for b in blocks if b.full_name not in existing_ids]
        if new:
            append[present_name] = diag_blocks.block_rows(new, derived, default)
    else:                                                          # no DiagnosisBlocks sheet -> create fresh
        new_sheets.append({"name": diag_blocks.DIAGBLOCKS_SHEET,
                           "rows": diag_blocks.diagnosis_blocks_grid(blocks, derived, default)})
