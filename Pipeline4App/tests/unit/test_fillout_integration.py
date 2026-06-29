"""ph200 integrated fill (domain/fillout/fill.fill_out) - the in-memory re-typing after 210, the
AD/AE/AF write-back cells, the DiagnosisBlocks append + derived recompute, and the no-op backup drop.

Hermetic: a tiny synthetic raw I/O List via openpyxl + a real staging read (the config CSVs ship with
the package), so the whole stage->fill->re-read flow exercises the integration without the real docs.
"""
import os
import tempfile

from openpyxl import Workbook, load_workbook

from _harness import run, eq, ok
from pipeline4.domain.fillout import fill, diag_blocks, diag_alloc

_SHEET = "NETSAFETY"


def _raw_iolist(path):
    """A raw I/O List with the columns staging reads by position (per column_map): F=ID, G=Bit, K/L=desc,
    O/P/Q = FU/Location/Device, R=Type, X=Mnemonic. AA..AG (the fill output columns) left BLANK."""
    wb = Workbook()
    ws = wb.active
    ws.title = _SHEET
    # a node head + two door channels on the same FLD (an indexable family that also diagnoses)
    ws["F2"] = "5"; ws["R2"] = "PLC"; ws["K2"] = "MAIN PLC NODE"; ws["O2"] = "=S1"
    ws["G3"] = "I0.0"; ws["K3"] = "DOOR OPEN"; ws["L3"] = "CH1"
    ws["O3"] = "=S1"; ws["P3"] = "+Z1"; ws["Q3"] = "-D9"; ws["AB3"] = "DI1/2"
    ws["G4"] = "I0.1"; ws["K4"] = "DOOR CLOSED"; ws["L4"] = "CH2"
    ws["O4"] = "=S1"; ws["P4"] = "+Z1"; ws["Q4"] = "-D9"; ws["AB4"] = "DD"
    wb.save(path)


def _params(path):
    return {"iolist_path": path,
            "iolist_params": {"sheets": _SHEET, "header_row": 1, "diag_bits_range": [0, 62]}}


def test_full_fill_writes_index_and_diag_cells():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "io.xlsx")
        _raw_iolist(p)
        res = fill.fill_out(_params(p))
        wb = load_workbook(p)
        ws = wb[_SHEET]
        # 220 wrote AD (index) for the door anchor; the door member inherits the same index by FLD
        ok(str(ws["AD3"].value or "").strip(), "AD index written for the DI1/2 anchor")
        ok(str(ws["AD4"].value or "").strip(), "AD index written for the DD member (inherited)")
        eq(ws["AD3"].value, ws["AD4"].value, "the door pair shares one index")
        # 230/240 wrote AE/AF (diag cabinet/bit) for the in-diag door rows
        ok(str(ws["AE3"].value or "").strip(), "AE diag_cabinet written")
        ok(str(ws["AF3"].value or "").strip(), "AF diag_bit written")
        eq(res["findings"] and [f.type for f in res["findings"] if f.severity == "FAIL"], [],
           "no blocking findings on a clean doc")


def test_diagnosisblocks_sheet_created_with_derived():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "io.xlsx")
        _raw_iolist(p)
        fill.fill_out(_params(p))
        wb = load_workbook(p)
        ok("DiagnosisBlocks" in wb.sheetnames, "a fresh DiagnosisBlocks sheet was created")
        ws = wb["DiagnosisBlocks"]
        header = [c.value for c in next(ws.iter_rows())]
        eq(header, diag_blocks.HEADERS, "the 10-column DiagnosisBlocks header")
        # at least one cabinet row with the derived Count/unused_bits columns populated
        body = list(ws.iter_rows(min_row=2, values_only=True))
        ok(body, "at least one cabinet row appended")
        ok(any(r[7] not in (None, "") for r in body), "Count (derived) populated")


def test_noop_drops_backup_on_prefilled_doc():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "io.xlsx")
        _raw_iolist(p)
        fill.fill_out(_params(p))                              # first run fills everything
        res2 = fill.fill_out(_params(p))                       # second run changes nothing
        eq(res2["backup"], "", "value-identical re-run drops its backup (no-op)")
        eq((res2["filled"], res2["index"], res2["diag"]), (0, 0, 0),
           "nothing re-filled (AB/AD/AE/AF already present)")


def test_retyping_after_210_feeds_220_230():
    # a row whose AB is BLANK gets Mode-1 classified, re-resolved to a `type`, and that type drives the
    # 220/230 legs - so a blank-AB diagnosable signal still receives an index + a diag slot.
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "io.xlsx")
        wb = Workbook()
        ws = wb.active
        ws.title = _SHEET
        ws["F2"] = "5"; ws["R2"] = "PLC"; ws["K2"] = "MAIN PLC NODE"; ws["O2"] = "=S1"
        # a blank-AB safety door input the rules classify to DI1/2
        ws["G3"] = "I0.0"; ws["K3"] = "SAFETY DOOR OPEN"; ws["L3"] = "CH1"
        ws["O3"] = "=S1"; ws["P3"] = "+Z1"; ws["Q3"] = "-D9"
        wb.save(p)
        fill.fill_out(_params(p))
        ws2 = load_workbook(p)[_SHEET]
        ab = str(ws2["AB3"].value or "").strip()
        ok(ab and ab != "<input required>", f"AB classified from the rules (got {ab!r})")
        ok(str(ws2["AC3"].value or "").strip(), "AC suggested written (always)")


def test_only_arg_restricts_writeback():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "io.xlsx")
        _raw_iolist(p)
        # only=210 writes AB/AC but NOT AD/AE/AF
        fill.fill_out(_params(p), only=210)
        ws = load_workbook(p)[_SHEET]
        eq(str(ws["AD3"].value or "").strip(), "", "only=210 leaves AD (index) blank")
        eq(str(ws["AE3"].value or "").strip(), "", "only=210 leaves AE (diag_cabinet) blank")
        # now only=220 fills AD but still not the diag cells
        fill.fill_out(_params(p), only=220)
        ws = load_workbook(p)[_SHEET]
        ok(str(ws["AD3"].value or "").strip(), "only=220 fills AD (index)")
        eq(str(ws["AE3"].value or "").strip(), "", "only=220 still leaves AE blank")


def test_diag_blocks_append_only_reuses_existing_id():
    # diag_blocks.read_existing reuses a present cabinet's ID_Local; block_rows appends only new cabinets.
    wb = Workbook()
    ws = wb.active
    ws.title = "DiagnosisBlocks"
    ws.append(diag_blocks.HEADERS)
    ws.append([5, 5, "=S1", "+OLD", "=S1+OLD", 1, "", 0, "", ""])
    ids, rows, header = diag_blocks.read_existing(wb)
    eq(ids, {"=S1+OLD": 5}, "existing FullName -> ID_Local reused")
    eq(rows, {5: 2}, "the existing cabinet's worksheet row")
    blocks = [diag_alloc.DiagBlock(id_local=5, fu="=S1", location="+OLD", full_name="=S1+OLD", template_type=1),
              diag_alloc.DiagBlock(id_local=6, fu="=S1", location="+NEW", full_name="=S1+NEW", template_type=1)]
    new = [b for b in blocks if b.full_name not in ids]
    appended = diag_blocks.block_rows(new, {}, (0, "", ""))
    eq(len(appended), 1, "only the NEW cabinet is appended")
    eq(appended[0][4], "=S1+NEW", "the appended row is the new FullName")


if __name__ == "__main__":
    import sys
    sys.exit(run("fillout_integration", [
        ("full_fill_writes_index_and_diag_cells", test_full_fill_writes_index_and_diag_cells),
        ("diagnosisblocks_sheet_created_with_derived", test_diagnosisblocks_sheet_created_with_derived),
        ("noop_drops_backup_on_prefilled_doc", test_noop_drops_backup_on_prefilled_doc),
        ("retyping_after_210_feeds_220_230", test_retyping_after_210_feeds_220_230),
        ("only_arg_restricts_writeback", test_only_arg_restricts_writeback),
        ("diag_blocks_append_only_reuses_existing_id", test_diag_blocks_append_only_reuses_existing_id),
    ]))
