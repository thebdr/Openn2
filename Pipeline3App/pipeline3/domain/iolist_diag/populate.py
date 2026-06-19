"""The phase-200 populator orchestrator.

Copies the source I/O List into the PopulatedIoList output (only when missing or older than the
source - so a re-fill picks up the user's manual edits in the SOURCE, while incremental column
fills accumulate in the copy), reads rows (data_only, with fonts for strike), computes script_type
(AB) + suggested (AC) + index (AD) + diag cabinet/bit (AE/AF), writes ONLY empty cells
(non-destructive; pre-filled cells are preserved + audit-logged), (re)writes the DiagnosisBlocks +
_UnresolvedIndex sheets, and reports unresolved entries (the caller halts the pipeline on those).
"""
from __future__ import annotations
import os
import shutil
from dataclasses import dataclass, field

from openpyxl import load_workbook

from pipeline3.core import config
from pipeline3.domain.iolist_diag import script_type as st, index_assign, diag_alloc, blocks as blk, report
from pipeline3.domain.iolist_diag.columns import ColumnResolver
from pipeline3.domain.iolist_diag.families import load_families, family_for
from pipeline3.domain.iolist_diag.models import IoRow, RowResult, INPUT_REQUIRED, DASH
from pipeline3.domain.iolist_diag.reader import read_iolist

ALL_COLS = ("script_type", "index", "diag_cabinet", "diag_bit")

# The output-column block (AA..AG) is unlabeled in the template; the populator writes these headers
# (their text comes from column_map.csv - no letter is hardcoded). Written only into a blank header
# cell, so a customized header is preserved.
HEADER_COLS = ("skip_reason", "script_type", "suggested_type", "index",
               "diag_cabinet", "diag_bit", "hardware_params")


def _blank(v) -> bool:
    """A cell counts as blank/overwritable if it is empty OR holds the <input required> sentinel
    from a prior run (a genuine human entry, anything else, is preserved)."""
    s = (v or "").strip()
    return (not s) or s == INPUT_REQUIRED


@dataclass
class PopulateResult:
    output_path: str
    sheets: list = field(default_factory=list)
    processed: int = 0
    indexed: int = 0
    diagnosed: int = 0
    unresolved: int = 0          # HALT count
    unknown: int = 0
    skipped: int = 0
    blocks: int = 0
    reported: int = 0
    audit: list = field(default_factory=list)
    skipped_sheets: list = field(default_factory=list)
    results: list = field(default_factory=list)

    @property
    def halt(self) -> bool:
        return self.unresolved > 0

    @property
    def counts(self) -> dict:
        return {"processed": self.processed, "indexed": self.indexed, "diag": self.diagnosed,
                "unresolved": self.unresolved, "unknown": self.unknown, "skipped": self.skipped}


def _skip_reason(io: IoRow, type_def: dict | None, params: dict) -> str:
    """The §5 skip classification. A struck row is excluded ONLY when strike_handling == 'exclude';
    for any other value ('error'/'ignore'/...) the row is KEPT (strike_handling only drives the
    validation severity later). Order matches Pipeline2."""
    strike_exclude = str(params.get("strike_handling", "exclude")).lower() == "exclude"
    sk = io.skip_reason_cell.strip()
    if io.mnemonic.strip() == DASH:
        return "mnemonic"
    if io.struck and strike_exclude:
        return "struck"
    # Skip Reason (AA) is honored only for a NON-struck row, so a struck row's exclusion is governed
    # purely by the strike rule (which respects strike_handling), not silently re-skipped via AA.
    if sk and sk not in ("0", "0.0") and not io.struck:
        return "skip_reason"
    if type_def is not None and not io.description and not io.has_device:
        return "spare"                                # a typed placeholder/SPARE row
    return ""


def _classify(io: IoRow, types: dict, fams: list, params: dict) -> RowResult:
    r = RowResult(iorow=io)
    suggested = st.suggested_type(io)
    computed = st.to_canonical(suggested, io)
    r.suggested_type = suggested
    r.computed_script_type = computed

    ex_ab = io.ex_script_type.strip()
    if ex_ab and ex_ab != INPUT_REQUIRED:             # Mode-2: preserve the human value, audit it
        r.script_type = ex_ab
        r.prefilled = True
        r.audit_mismatch = bool(computed) and computed not in (r.script_type, INPUT_REQUIRED)
    else:                                             # Mode-1: write the computed value
        r.script_type = computed

    r.type_def = config.resolve_type(types, r.script_type)
    r.family = family_for(r.script_type, fams)
    r.unknown_type = bool(r.script_type) and r.script_type != INPUT_REQUIRED \
        and r.type_def is None and r.family is None

    reason = _skip_reason(io, r.type_def, params)
    if reason:
        r.skipped = True
        r.skip_reason = reason
    return r


def _write_row(ws, cr, r, write: set) -> None:
    io = r.iorow
    if "script_type" in write:
        if _blank(io.ex_script_type) and r.script_type:
            cr.set(ws, io.row, "script_type", r.script_type)
        # AC = the auto-inferred CANONICAL script type, kept for reference (== AB in Mode-1; in
        # Mode-2 it shows what the tool would have suggested vs the hand-entered AB). It is a
        # derived column, so it is refreshed (overwritten) each run to stay current.
        if "suggested_type" in cr and r.computed_script_type:
            cr.set(ws, io.row, "suggested_type", r.computed_script_type)
    if "index" in write and _blank(io.ex_index) and r.index:
        cr.set(ws, io.row, "index", r.index)
    if "diag_cabinet" in write and _blank(io.ex_diag_cabinet) and r.diag_cabinet:
        cr.set(ws, io.row, "diag_cabinet", r.diag_cabinet)
    if "diag_bit" in write and _blank(io.ex_diag_bit) and r.diag_bit:
        cr.set(ws, io.row, "diag_bit", r.diag_bit)


def _write_headers(ws, cr, header_row: int) -> None:
    """Write the column_map headers for the AA..AG output block into a blank header cell."""
    for canon in HEADER_COLS:
        if canon not in cr:
            continue
        hdr = cr.expected_header(canon)
        cur = cr.get(ws, header_row, canon)
        if hdr and (cur is None or str(cur).strip() == ""):
            cr.set(ws, header_row, canon, hdr)


def _ensure_dest(src: str, dest_dir: str) -> str:
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, os.path.basename(src))
    if not os.path.exists(dest) or os.path.getmtime(src) > os.path.getmtime(dest):
        shutil.copy2(src, dest)
    return dest


def populate(params: dict, write=None, out_dir: str | None = None, emit=print) -> PopulateResult:
    write = set(write) if write is not None else set(ALL_COLS)
    src = params.get("io_list", {}).get("path")
    if not src or not os.path.exists(src):
        raise ValueError(f"I/O List not found: {src}")
    out_root = out_dir or config.output_root(params)
    dest = _ensure_dest(src, config.out_path(out_root, "populated_iolist"))

    cr = ColumnResolver("IoList")
    wb_vals = load_workbook(dest, data_only=True)
    rows, sheets, skipped_sheets = read_iolist(wb_vals, params, cr)
    wb_vals.close()
    emit(f"I/O sheets processed: {', '.join(sheets)}")
    for s in skipped_sheets:
        emit(f"  skipped sheet (no io_list.sheet match): {s}")

    types = config.load_signal_types()
    fams = load_families()
    results = [_classify(io, types, fams, params) for io in rows]
    index_assign.assign_indices(results, fams)
    block_list = diag_alloc.allocate(results, params)

    wb = load_workbook(dest)
    header_row = int(params.get("io_list", {}).get("header_row", 1) or 1)
    for name in sheets:
        _write_headers(wb[name], cr, header_row)
    for r in results:
        _write_row(wb[r.iorow.sheet], cr, r, write)
    wrote_diag = bool(write & {"diag_cabinet", "diag_bit"})
    if wrote_diag:
        blk.write_diagnosis_blocks(wb, block_list, results)
    reported = report.write_unresolved_sheet(wb, results, cr)
    wb.save(dest)

    res = PopulateResult(
        output_path=dest, sheets=sheets, results=results,
        processed=len(results),
        indexed=sum(1 for r in results if r.index and r.index != INPUT_REQUIRED),
        diagnosed=sum(1 for r in results if r.diag_cabinet),
        unresolved=sum(1 for r in results if not r.skipped and (r.script_type == INPUT_REQUIRED or r.unresolved)),
        unknown=sum(1 for r in results if not r.skipped and r.unknown_type),
        skipped=sum(1 for r in results if r.skipped),
        blocks=len(block_list) if wrote_diag else 0,
        reported=reported,
        audit=report.audit_lines(results),
        skipped_sheets=skipped_sheets,
    )
    emit(report.summary(res.counts))
    emit(f"populated I/O List -> {dest}")
    return res
