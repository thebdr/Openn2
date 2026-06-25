"""The phase-200 populator orchestrator.

Fills the SOURCE I/O List **in place** - after a fill the source workbook IS the populated document
(so the next fill picks up any manual edits, and staging/validation read the filled source). Reads
rows (data_only, with fonts for strike), computes script_type (AB) + suggested (AC) + index (AD) +
diag cabinet/bit (AE/AF), writes ONLY empty cells (non-destructive; pre-filled cells are preserved +
audit-logged), (re)writes the DiagnosisBlocks + _UnresolvedIndex sheets, and reports unresolved
entries (the caller halts the pipeline on those). Idempotent: a re-run fills nothing new.
"""
from __future__ import annotations
import datetime
import os
import shutil
from dataclasses import dataclass, field

from openpyxl import load_workbook

from pipeline3.core import config
from pipeline3.io import xlsx_edit
from pipeline3.domain.iolist_diag import script_type as st, index_assign, diag_alloc, blocks as blk, report
from pipeline3.domain.iolist_diag.columns import ColumnResolver
from pipeline3.domain.iolist_diag.families import load_families, family_for
from pipeline3.domain.iolist_diag.models import (IoRow, RowResult, INPUT_REQUIRED, DASH,
                                                 DIAGBLOCKS_SHEET, DIAGBLOCKS_LEGACY, UNRESOLVED_SHEET)
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
    backup: str = ""             # timestamped backup kept (changed); "" when none/removed (no change)

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
    computed = st.suggested_type(io)      # the §6 ladder yields the canonical script_type directly
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


def _collect_row(edits: dict, cr, r, write: set) -> None:
    """Record one row's AB..AF fills into `edits` ({cell_ref: value}) - the surgical equivalent of the
    old openpyxl _write_row. AC (suggested_type) is ALWAYS written (the app-owned derived column, kept
    current); the input columns only when the existing cell is blank (non-destructive)."""
    io = r.iorow
    if "script_type" in write:
        if _blank(io.ex_script_type) and r.script_type:
            edits[f"{cr.letter('script_type')}{io.row}"] = r.script_type
        if "suggested_type" in cr and r.computed_script_type:
            edits[f"{cr.letter('suggested_type')}{io.row}"] = r.computed_script_type
    if "index" in write and _blank(io.ex_index) and r.index:
        edits[f"{cr.letter('index')}{io.row}"] = r.index
    if "diag_cabinet" in write and _blank(io.ex_diag_cabinet) and r.diag_cabinet:
        edits[f"{cr.letter('diag_cabinet')}{io.row}"] = r.diag_cabinet
    if "diag_bit" in write and _blank(io.ex_diag_bit) and r.diag_bit:
        edits[f"{cr.letter('diag_bit')}{io.row}"] = r.diag_bit


def _collect_headers(edits: dict, cr, header_row: int, header_vals: dict) -> None:
    """Record the AA..AG column_map headers into `edits`, only where the existing header cell is blank."""
    for canon in HEADER_COLS:
        if canon not in cr:
            continue
        hdr = cr.expected_header(canon)
        cur = header_vals.get(canon)
        if hdr and (cur is None or str(cur).strip() == ""):
            edits[f"{cr.letter(canon)}{header_row}"] = hdr


def _backup_path(src: str) -> str:
    """A timestamped, collision-free backup path beside the source: <base>.bak_<YYYYMMDD_HHMMSS><ext>."""
    base, ext = os.path.splitext(src)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    cand = f"{base}.bak_{ts}{ext}"
    i = 1
    while os.path.exists(cand):
        cand = f"{base}.bak_{ts}_{i}{ext}"
        i += 1
    return cand


def _same_content(a: str, b: str) -> bool:
    """True if two workbooks have identical sheet names + cell values (ignores file metadata - an
    openpyxl re-save perturbs the bytes but not the values, so an idempotent re-fill compares equal)."""
    wa, wbk = load_workbook(a), load_workbook(b)
    try:
        if wa.sheetnames != wbk.sheetnames:
            return False
        for nm in wa.sheetnames:
            sa, sb = wa[nm], wbk[nm]
            if sa.max_row != sb.max_row or sa.max_column != sb.max_column:
                return False
            for row in sa.iter_rows():
                for cell in row:
                    if cell.value != sb[cell.coordinate].value:
                        return False
        return True
    finally:
        wa.close()
        wbk.close()


def populate(params: dict, write=None, out_dir: str | None = None, emit=print) -> PopulateResult:
    # out_dir is retained for call-site compatibility but no longer used: the populator now fills
    # the SOURCE I/O List in place (it becomes the populated document) instead of a copy.
    write = set(write) if write is not None else set(ALL_COLS)
    _sink = emit                            # normalize: forward `type` to a kwarg-aware sink (ctx.emit),

    def emit(*a, type=""):                  # else drop it - so any plain callable still works as `emit`
        try:
            _sink(*a, type=type)
        except TypeError:
            _sink(*a)
    src = params.get("io_list", {}).get("path")
    if not src or not os.path.exists(src):
        raise ValueError(f"I/O List not found: {src}")
    dest = src
    # Snapshot the source BEFORE editing; kept only if the fill actually changes the file (below).
    backup = _backup_path(src)
    shutil.copy2(src, backup)

    cr = ColumnResolver("IoList")
    header_row = int(params.get("io_list", {}).get("header_row", 1) or 1)
    wb_vals = load_workbook(dest, data_only=True)
    rows, sheets, skipped_sheets = read_iolist(wb_vals, params, cr)
    header_vals = {name: {c: cr.get(wb_vals[name], header_row, c) for c in HEADER_COLS if c in cr}
                   for name in sheets}
    existing_blocks, rows_by_cid, blk_header = blk.read_existing(wb_vals)   # ids (reuse) + rows + header
    present_name = next((s for s in wb_vals.sheetnames
                         if s.strip().lower() in (DIAGBLOCKS_SHEET.lower(), DIAGBLOCKS_LEGACY.lower())), None)
    wb_vals.close()
    emit(f"I/O sheets processed: {', '.join(sheets)}", type="sheets")
    for s in skipped_sheets:
        emit(f"  skipped sheet (no io_list.sheet match): {s}", type="sheet_skipped")

    types = config.load_signal_types()
    fams = load_families()
    results = [_classify(io, types, fams, params) for io in rows]
    index_assign.assign_indices(results, fams)
    block_list = diag_alloc.allocate(results, params, existing=existing_blocks)

    # SURGICAL write (io.xlsx_edit): edit ONLY the filled cells + (re)build the app-owned sheets, byte-
    # copying every other part. An openpyxl load->save would FLATTEN the template's dynamic-array
    # formulas into an overlapping-array CORRUPTION (and drop formula caches); editing in place avoids
    # both. A fill that lands in an array spill freezes that array to its cached values (logged WARN).
    cell_edits = {name: {} for name in sheets}
    for name in sheets:
        _collect_headers(cell_edits[name], cr, header_row, header_vals[name])
    for r in results:
        _collect_row(cell_edits[r.iorow.sheet], cr, r, write)
    wrote_diag = bool(write & {"diag_cabinet", "diag_bit"})
    new_sheets, append = [], {}
    if wrote_diag:
        # Count + unused_bits + non_unique_bits are DERIVED from the REAL post-fill (Diag_Cabinet, Diag_Bit)
        # of every relevant row (ex value if present, else what this run writes), recomputed every run.
        min_b = int(params.get("diag_bit_min", 0) or 0)
        max_b = int(params.get("diag_bit_max", 62) or 62)
        placed = []
        for r in results:
            io = r.iorow
            cab = (blk._norm_cab(io.ex_diag_cabinet) if not _blank(io.ex_diag_cabinet)
                   else (r.diag_cabinet if "diag_cabinet" in write else ""))
            if not cab:
                continue
            bit = (blk._bit_int(io.ex_diag_bit) if not _blank(io.ex_diag_bit)
                   else (blk._bit_int(r.diag_bit) if "diag_bit" in write else None))
            placed.append((cab, bit))
        derived = blk.analyze(placed, min_b, max_b)
        default = (0, blk._fmt_ranges(range(min_b, max_b + 1)), "")
        if present_name:                                # APPEND-ONLY identity; REFRESH derived columns
            cell_edits.setdefault(present_name, {}).update(
                blk.derived_edits(blk_header, rows_by_cid, derived, default))
            new = [b for b in block_list if b.full_name not in existing_blocks]   # add only missing cabinets
            if new:
                append[present_name] = blk.block_rows(new, derived, default)
        else:                                           # no DiagnosisBlocks sheet yet -> create it fresh
            new_sheets.append({"name": DIAGBLOCKS_SHEET,
                               "rows": blk.diagnosis_blocks_grid(block_list, derived, default)})
    unres_rows, unres_links = report.unresolved_grid(results, cr)
    new_sheets.append({"name": UNRESOLVED_SHEET, "rows": unres_rows, "hyperlinks": unres_links})
    reported = len(unres_links)
    frozen = xlsx_edit.edit_workbook(
        dest, cell_edits={k: v for k, v in cell_edits.items() if v}, new_sheets=new_sheets,
        append_rows=append or None)
    for sheet_name, master, rng in frozen:
        emit(f"[WARN] froze legacy array formula {sheet_name}!{master} (spill {rng}) to its cached "
             "values - the original formula is preserved in the backup", type="array_frozen")

    # Keep the backup only if the fill changed the file; otherwise delete it (no-op re-fill).
    if _same_content(backup, dest):
        os.remove(backup)
        backup = ""

    res = PopulateResult(
        output_path=dest, sheets=sheets, results=results, backup=backup,
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
    emit(report.summary(res.counts), type="summary")
    emit(f"populated I/O List -> {dest}", type="populated")
    emit(f"backup -> {os.path.basename(backup)}" if backup else "no changes - backup removed", type="backup")
    return res
