"""§10 the _UnresolvedIndex audit sheet + the console summary + Mode-2 audit lines.

Six distinct unresolved reasons can show up; each unresolved/unknown row gets one clickable
internal hyperlink to the exact cell that needs attention.
"""
from __future__ import annotations

from pipeline3.domain.iolist_diag.models import INPUT_REQUIRED, UNRESOLVED_SHEET

# the six reasons (EN; i18n wiring is a later polish)
REASONS = {
    "unmatched_type":       "Type could not be auto-classified - enter the Script Type by hand.",
    "unknown_type":         "Script Type is not in the catalogue (signal_types.csv).",
    "manual_member":        "Door relay/lamp/unlock - index cannot be auto-linked.",
    "channel_fld_mismatch": "Channel partner missing or FLD mismatch between the two channels.",
    "ki_without_kq":        "Contactor feedback (KI) has no matching output (KQ) by FLD / not contiguous.",
    "door_member_unlinked": "Door member (DD / DI ch.2) has no DI ch.1 anchor by FLD.",
}


def needs_attention(r):
    """Return (canonical_column, reason_key) if the row needs manual attention, else None."""
    if r.skipped:
        return None
    if r.script_type == INPUT_REQUIRED:
        return ("script_type", "unmatched_type")
    if r.unresolved:
        return ("index", r.unresolved_reason or "manual_member")
    if r.unknown_type:
        return ("script_type", "unknown_type")
    return None


def unresolved_grid(results: list, cr) -> tuple:
    """(rows, hyperlinks) for the _UnresolvedIndex sheet, for the surgical writer (io.xlsx_edit). One row
    per attention-needing result; the Source cell (col A) links INTERNALLY to the exact cell that needs
    fixing ('Sheet'!<col><row>). Mirrors write_unresolved_sheet's columns + links."""
    rows = [["Source", "Script Type", "Device (FLD)", "Description", "Reason"]]
    links = []
    out = 2
    for r in results:
        att = needs_attention(r)
        if not att:
            continue
        canon, reason = att
        io = r.iorow
        rows.append([f"{io.sheet} - Row {io.row} - {r.script_type or '?'}",
                     "" if r.script_type == INPUT_REQUIRED else r.script_type,
                     io.fld, io.description, REASONS.get(reason, reason)])
        links.append((f"A{out}", f"'{io.sheet}'!{cr.letter(canon)}{io.row}", f"{io.sheet} - Row {io.row}"))
        out += 1
    return rows, links


def write_unresolved_sheet(wb, results: list, cr) -> int:
    for name in list(wb.sheetnames):
        if name.strip().lower() == UNRESOLVED_SHEET.lower():
            del wb[name]
    ws = wb.create_sheet(UNRESOLVED_SHEET)
    ws.append(["Source", "Script Type", "Device (FLD)", "Description", "Reason"])
    out = 2
    n = 0
    for r in results:
        att = needs_attention(r)
        if not att:
            continue
        canon, reason = att
        io = r.iorow
        col = cr.letter(canon)
        link_cell = ws.cell(out, 1, f"{io.sheet} - Row {io.row} - {r.script_type or '?'}")
        link_cell.hyperlink = f"#'{io.sheet}'!{col}{io.row}"
        link_cell.style = "Hyperlink"
        ws.cell(out, 2, "" if r.script_type == INPUT_REQUIRED else r.script_type)
        fld_cell = ws.cell(out, 3, io.fld)
        fld_cell.data_type = "s"
        ws.cell(out, 4, io.description)
        ws.cell(out, 5, REASONS.get(reason, reason))
        out += 1
        n += 1
    return n


def audit_lines(results: list) -> list:
    """One line per Mode-2 (pre-filled Script Type) row; flags a mismatch vs the computed value."""
    lines = []
    for r in results:
        if not r.prefilled:
            continue
        io = r.iorow
        flag = "  <-- MISMATCH" if r.audit_mismatch else ""
        lines.append(f"{io.sheet}!{io.row}  FLD={io.fld}  '{io.desc_l1}' '{io.desc_l1b}'  "
                     f"existing={r.script_type!r} computed={r.computed_script_type!r}{flag}")
    return lines


def summary(counts: dict) -> str:
    return ("{processed} rows | {indexed} indexed | {diag} diagnosed | {unresolved} unresolved | "
            "{unknown} unknown-type | {skipped} skipped").format(**counts)
