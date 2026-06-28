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
from pipeline4.core.finding import Finding
from pipeline4.domain.fillout import classify, reader
from pipeline4.io import xlsx_edit

INPUT_REQUIRED = classify.INPUT_REQUIRED
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
        desc = (classify.clean(raw.get("desc_l1")) + " " + classify.clean(raw.get("desc_l1b"))).strip()
        rows.append([f"{sheet} - Row {rownum}", "", fld, desc, "unmatched type"])
        links.append((f"A{i}", f"'{sheet}'!{ab_col}{rownum}", f"{sheet} - Row {rownum}"))
    return {"name": _UNRESOLVED_SHEET, "rows": rows, "hyperlinks": links}


def fill_script_type(params: dict | None = None) -> dict:
    """Fill AB/AC in the source I/O List in place. Returns
    {output_path, backup, findings, filled, mismatch, unresolved}. NEVER writes the SSOT."""
    params = params or config.load_params()
    io_path = params.get("iolist_path")
    if not io_path or not os.path.exists(io_path):
        return {"output_path": io_path or "", "backup": "", "filled": 0, "mismatch": 0, "unresolved": 0,
                "findings": [_f("fill_no_iolist", "FAIL", f"I/O List not found: {io_path!r}", io_path or "")]}

    colmap = config.load_column_map("IoList")
    gate_rules, type_rules = config.load_gate_rules(), config.load_script_type_rules()
    header_row = int(config.get_param(params, "iolist_params.header_row", 1) or 1)
    rows = reader.read_rows(params)

    def _letter(canon):
        return next((m["column"] for m in colmap if m["canonical"] == canon), None)

    def _header(canon):
        return next((m["expected_header"] for m in colmap if m["canonical"] == canon), "")

    ab, ac = _letter("script_type"), _letter("suggested_type")
    sheets = list(dict.fromkeys(r["source_sheet"] for r in rows))      # matched sheets, in order
    headers = _read_output_headers(io_path, sheets, colmap, header_row)

    cell_edits: dict = defaultdict(dict)
    findings, unresolved = [], []
    filled = mismatch = 0

    for sheet in sheets:                                              # the output-column headers (if blank)
        for canon in _OUTPUT_COLS:
            col, hdr = _letter(canon), _header(canon)
            cur = headers.get(sheet, {}).get(canon)
            if col and hdr and (cur is None or str(cur).strip() == ""):
                cell_edits[sheet][f"{col}{header_row}"] = hdr

    for raw in rows:
        sheet, rownum = raw["source_sheet"], raw["source_row"]
        computed = classify.classify(raw, gate_rules, type_rules)
        if ac and computed:
            cell_edits[sheet][f"{ac}{rownum}"] = computed           # AC: always the computed value
        ex_ab = str(raw.get("script_type") or "").strip()
        if ex_ab and ex_ab != INPUT_REQUIRED:                       # Mode-2: preserve the human value
            value = ex_ab
            if computed and computed not in (ex_ab, INPUT_REQUIRED):
                mismatch += 1
                findings.append(_f("fill_type_mismatch", "WARN",
                                   f"kept the existing script type {ex_ab!r}; the rules computed {computed!r}",
                                   f"{sheet}!{ab}{rownum}"))
        else:                                                       # Mode-1: write the computed value to AB
            value = computed
            if ab and computed:
                cell_edits[sheet][f"{ab}{rownum}"] = computed
                if computed != INPUT_REQUIRED:
                    filled += 1
        if value == INPUT_REQUIRED and not _skipped(raw):
            unresolved.append(raw)
            findings.append(_f("fill_unresolved", "FAIL",
                               "the description matched no script-type rule - fill it in the source I/O List",
                               f"{sheet}!{ab}{rownum}"))

    backup = _backup_path(io_path)
    shutil.copy2(io_path, backup)
    frozen = xlsx_edit.edit_workbook(io_path, cell_edits={s: e for s, e in cell_edits.items() if e},
                                     new_sheets=[_unresolved_sheet(unresolved, ab)])
    for sheet, master, rng in frozen:
        findings.append(_f("fill_array_frozen", "WARN",
                           f"froze a dynamic array (spill {rng}) the fill landed in", f"{sheet}!{master}"))
    if _same_content(backup, io_path):                              # no-op -> drop the backup
        os.remove(backup)
        backup = ""
    return {"output_path": io_path, "backup": backup, "findings": findings,
            "filled": filled, "mismatch": mismatch, "unresolved": len(unresolved)}
