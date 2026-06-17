"""Task E - the unresolved-index report + the user-facing summary / audit (spec §10, §6).

`needs_attention` flags every row that needs manual entry: an unmatched script_type (the `<input
required>` marker in AB) or an index that couldn't be auto-resolved (the marker in AD). They are
listed in an in-workbook `_UnresolvedIndex` sheet, each with a CLICKABLE internal hyperlink to the
exact cell to fill, and counted for the console/log summary. `audit_lines` emits one line per
pre-filled script_type row (Mode 2) so the engineer gets a full diff of human entries vs computed.
"""
from __future__ import annotations

from pipeline2.core import i18n
from pipeline2.iolist_diag.columns import ColumnResolver
from pipeline2.iolist_diag.models import INPUT_REQUIRED, RowResult, UNRESOLVED_SHEET


def needs_attention(r: RowResult) -> tuple[str, str] | None:
    """(canonical_column, reason_key) for a row the engineer must look at, else None.
    Unmatched type / unknown (not-in-catalogue) type -> the script_type cell; unresolved index ->
    the index cell. Unknown types are reported (§6) but do not by themselves halt the run (that is
    gated on the `<input required>` markers - see populate)."""
    if r.skipped:
        return None
    if r.script_type == INPUT_REQUIRED:
        return ("script_type", "unmatched_type")
    if r.unresolved:
        return ("index", r.unresolved_reason or "manual_member")
    if r.unknown_type:
        return ("script_type", "unknown_type")
    return None


def attention(results: list[RowResult]) -> list[tuple[RowResult, str, str]]:
    out = []
    for r in results:
        hit = needs_attention(r)
        if hit:
            out.append((r, hit[0], hit[1]))
    return out


def write_unresolved_sheet(wb, results: list[RowResult], cr: ColumnResolver, lang: str = "en") -> int:
    """(Re)create the `_UnresolvedIndex` sheet with one clickable row per entry. Returns the count."""
    rows = attention(results)
    for name in list(wb.sheetnames):
        if name.strip().lower() == UNRESOLVED_SHEET.lower():
            del wb[name]
    ws = wb.create_sheet(UNRESOLVED_SHEET)
    headers = [i18n.tr(k, lang) for k in
               ("idiag_ur_h_row", "idiag_ur_h_type", "idiag_ur_h_fld", "idiag_ur_h_desc", "idiag_ur_h_reason")]
    for c, h in enumerate(headers, 1):
        ws.cell(row=1, column=c, value=h)
    for i, (r, canon, reason) in enumerate(rows):
        out_row = 2 + i
        io = r.iorow
        col = cr.letter(canon)
        link = ws.cell(row=out_row, column=1, value=f"Row {io.row} - {r.script_type or '?'}")
        link.hyperlink = f"#'{io.sheet}'!{col}{io.row}"      # jump to the exact cell to fill
        link.style = "Hyperlink"
        ws.cell(row=out_row, column=2, value="" if r.script_type == INPUT_REQUIRED else r.script_type)
        fld = ws.cell(row=out_row, column=3, value=io.fld)         # FLD starts with '=' -> force text
        fld.data_type = "s"
        ws.cell(row=out_row, column=4, value=io.description)
        ws.cell(row=out_row, column=5, value=i18n.tr(f"idiag_reason_{reason}", lang))
    return len(rows)


def summary_line(counts: dict, lang: str = "en") -> str:
    return i18n.tr("idiag_summary", lang, **counts)


def audit_lines(results: list[RowResult], lang: str = "en") -> list[str]:
    """One line per pre-filled (Mode-2) script_type row: row, descriptions, FLD, existing vs computed."""
    lines = []
    for r in results:
        if not r.prefilled:
            continue
        io = r.iorow
        flag = "  <-- MISMATCH" if r.audit_mismatch else ""
        lines.append(
            f"{io.sheet}!{io.row}  FLD={io.fld}  '{io.desc_l1}' '{io.desc_l1b}'  "
            f"existing={r.script_type!r} computed={r.computed_script_type!r}{flag}")
    return lines
