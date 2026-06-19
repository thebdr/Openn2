"""M4 gate (data-independent): the phase-200 populator on a synthetic I/O List.

Covers: node-meta row skipped, the suggested-type ladder (alarm A, emergency-PB channel pair),
canonical mapping, index assignment (channel pairing -> shared index), diagnosis allocation
(node cabinet for A; Type-2 block for E1/2), idempotency, and DiagnosisBlocks creation.
"""
import os
import shutil
import tempfile
from _harness import run, eq, ok
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font
from openpyxl.utils import column_index_from_string as CI

from pipeline3.core import config
from pipeline3.domain.iolist_diag import populate as pop
from pipeline3.domain.iolist_diag import script_type as st
from pipeline3.domain.iolist_diag.models import DIAGBLOCKS_SHEET, IoRow


def _set(ws, col, row, val, text=False):
    c = ws.cell(row=row, column=CI(col), value=val)
    if text:
        c.data_type = "s"
    return c


def _make_iolist(path):
    wb = Workbook()
    ws = wb.active
    ws.title = "NET SAFETY 50"
    # header row 1 (positions matter, not text)
    for col, name in (("F", "ID"), ("G", "Bit"), ("K", "Desc1"), ("L", "Desc1b"),
                      ("O", "Functional unit"), ("P", "Location"), ("Q", "Device"), ("R", "Type")):
        _set(ws, col, 1, name)
    # row 2: node-meta "50" line -> must be skipped (no FU, no I/Q addr, no script_type)
    _set(ws, "F", 2, 50)
    _set(ws, "K", 2, "Profinet Network")
    # row 3: an alarm input (type A in col R)
    _set(ws, "G", 3, "I1.0"); _set(ws, "K", 3, "CIRCUIT BREAKER TRIPPED")
    _set(ws, "O", 3, "=S1", text=True); _set(ws, "P", 3, "+MS1.CC1", text=True)
    _set(ws, "Q", 3, "-F09001", text=True); _set(ws, "R", 3, "A")
    # rows 4/5: an emergency push-button channel pair (same FLD)
    for r, ch, dev in ((4, "CH1", "-S001"), (5, "CH2", "-S001")):
        _set(ws, "G", r, f"I2.{r-4}")
        _set(ws, "K", r, "EMERGENCY PUSH-BUTTON PRESSED")
        _set(ws, "L", r, ch)
        _set(ws, "O", r, "=S1", text=True); _set(ws, "P", r, "+MS1.CC1", text=True)
        _set(ws, "Q", r, dev, text=True)
    wb.save(path)


def _params(io_path):
    p = config.load_params()
    p["io_list"] = {"path": io_path, "sheet": ["NET SAFETY 50"], "header_row": 1}
    return p


def _by_addr(results, addr):
    return next(r for r in results if r.iorow.addr == addr)


def _run(fn):
    with tempfile.TemporaryDirectory() as d:
        io = os.path.join(d, "iolist.xlsx")
        out = os.path.join(d, "out")
        _make_iolist(io)
        params = _params(io)
        params["output_dir"] = out
        fn(params, out, d)


def test_populates_and_skips_nodemeta():
    def check(params, out, d):
        res = pop.populate(params, out_dir=out, emit=lambda *_: None)
        eq(res.processed, 3, "node-meta row 2 skipped; 3 data rows")
        eq(res.unresolved, 0)
        ok(not res.halt)
    _run(check)


def test_script_type_and_index():
    def check(params, out, d):
        res = pop.populate(params, out_dir=out, emit=lambda *_: None)
        a = _by_addr(res.results, "I1.0")
        e1 = _by_addr(res.results, "I2.0")
        e2 = _by_addr(res.results, "I2.1")
        eq(a.script_type, "A")
        eq(e1.script_type, "E1/2")
        eq(e2.script_type, "E2/2")
        eq(e1.index, "0001")
        eq(e2.index, "0001", "channel-2 inherits the anchor's index by FLD")
        eq(a.index, "0001", "standalone A on its own counter")
    _run(check)


def test_diag_allocation():
    def check(params, out, d):
        res = pop.populate(params, out_dir=out, emit=lambda *_: None)
        a = _by_addr(res.results, "I1.0")
        e1 = _by_addr(res.results, "I2.0")
        e2 = _by_addr(res.results, "I2.1")
        ok(a.diag_cabinet and a.diag_bit, "alarm A diagnosed in a node cabinet")
        eq(a.diag_cabinet, "000")
        eq(a.diag_bit, "00")
        ok(e1.diag_cabinet and e1.diag_cabinet != "000", "E1/2 in a Type-2 block")
        eq(e2.diag_cabinet, "", "E2/2 is not in_diag")
        ok(res.blocks >= 2, f"node + Type-2 blocks, got {res.blocks}")
    _run(check)


def test_writes_columns_and_diagblocks():
    def check(params, out, d):
        res = pop.populate(params, out_dir=out, emit=lambda *_: None)
        wb = load_workbook(res.output_path)
        ok(DIAGBLOCKS_SHEET in wb.sheetnames, "DiagnosisBlocks sheet written")
        ws = wb["NET SAFETY 50"]
        eq(ws.cell(3, CI("AB")).value, "A")
        eq(ws.cell(4, CI("AB")).value, "E1/2")
        eq(ws.cell(4, CI("AD")).value, "0001")     # index written
        # AC = the auto-inferred canonical, kept for reference (== AB in Mode-1)
        eq(ws.cell(3, CI("AC")).value, "A")
        eq(ws.cell(4, CI("AC")).value, "E1/2")
        # the output-column headers are written from column_map (template left them blank)
        eq(ws.cell(1, CI("AA")).value, "Skip Reason")
        eq(ws.cell(1, CI("AB")).value, "Script Type")
        eq(ws.cell(1, CI("AC")).value, "Suggested Type")
        eq(ws.cell(1, CI("AD")).value, "Index")
        eq(ws.cell(1, CI("AE")).value, "Diag Cabinet")
        eq(ws.cell(1, CI("AF")).value, "Diag Bit")
        eq(ws.cell(1, CI("AG")).value, "Hardware Parameters")
        wb.close()
    _run(check)


def test_fire_alarm_rung():
    r1 = IoRow(sheet="s", row=1, addr="I20.3", desc_l1="FIRE ALARM", desc_l1b="CH1")
    r2 = IoRow(sheet="s", row=2, addr="I20.7", desc_l1="FIRE ALARM", desc_l1b="CH2")
    eq(st.suggested_type(r1), "F1/2", "fire alarm CH1 -> F1/2 (like E1/2)")
    eq(st.suggested_type(r2), "F2/2", "fire alarm CH2 -> F2/2")


def test_ladder_yields_canonical_directly():
    # the legacy ENC/FA/RES intermediates are gone: the ladder returns N/Z/R directly (== AB).
    enc = IoRow(sheet="s", row=1, addr="I3.0", desc_l1="SAFETY ENCODER PHOTOCELL", desc_l1b="CELL 1")
    eq(st.suggested_type(enc), "N1/2", "encoder -> N, not legacy ENC")
    fa = IoRow(sheet="s", row=2, addr="Q3.0", desc_l1="INDICATOR", desc_l1b="EMERGENCY AREA 3")
    eq(st.suggested_type(fa), "Z3", "emergency-area output -> Z, not legacy FA")
    res = IoRow(sheet="s", row=3, addr="I3.1", desc_l1="EMERGENCY RESET", desc_l1b="")
    eq(st.suggested_type(res), "R*", "reset without an area -> R*, not legacy RES")
    res2 = IoRow(sheet="s", row=4, addr="I3.2", desc_l1="EMERGENCY RESET", desc_l1b="AREA 2")
    eq(st.suggested_type(res2), "R2", "reset with an area -> R<area>")


def test_strike_handling():
    def build(path):
        wb = Workbook(); ws = wb.active; ws.title = "NET SAFETY 50"
        for col, name in (("G", "Bit"), ("K", "D1"), ("O", "FU"), ("P", "Loc"), ("Q", "Dev"), ("R", "Type")):
            _set(ws, col, 1, name)
        _set(ws, "G", 2, "I1.0"); _set(ws, "K", 2, "CIRCUIT BREAKER TRIPPED")
        _set(ws, "O", 2, "S1"); _set(ws, "P", 2, "M1"); _set(ws, "Q", 2, "-F1", text=True); _set(ws, "R", 2, "A")
        _set(ws, "G", 3, "I1.1"); _set(ws, "K", 3, "CIRCUIT BREAKER TRIPPED")
        _set(ws, "O", 3, "S1"); _set(ws, "P", 3, "M1"); _set(ws, "Q", 3, "-F2", text=True); _set(ws, "R", 3, "A")
        ws.cell(3, CI("G")).font = Font(strike=True)        # row 3 is struck
        wb.save(path)

    with tempfile.TemporaryDirectory() as d:
        io = os.path.join(d, "io.xlsx"); out = os.path.join(d, "out"); build(io)
        params = _params(io); params["output_dir"] = out

        params["strike_handling"] = "exclude"
        r = pop.populate(params, out_dir=out, emit=lambda *_: None)
        s = _by_addr(r.results, "I1.1")
        ok(s.skipped and s.skip_reason == "struck", "exclude -> struck row skipped")

        shutil.rmtree(out, ignore_errors=True)              # fresh copy for the second run
        params["strike_handling"] = "ignore"
        r2 = pop.populate(params, out_dir=out, emit=lambda *_: None)
        s2 = _by_addr(r2.results, "I1.1")
        ok(not s2.skipped, "ignore -> struck row kept")
        eq(s2.script_type, "A", "kept struck row is populated normally")


def test_multi_sheet_global_and_skip_log():
    def build(path):
        wb = Workbook()
        cover = wb.active; cover.title = "COVER"; cover["A1"] = "cover page"
        for sname in ("NET SAFETY 50", "NET SAFETY 51"):
            ws = wb.create_sheet(sname)
            for col, name in (("G", "Bit"), ("K", "D1"), ("O", "FU"), ("P", "Loc"), ("Q", "Dev"), ("R", "Type")):
                _set(ws, col, 1, name)
            _set(ws, "G", 2, "I1.0"); _set(ws, "K", 2, "CIRCUIT BREAKER TRIPPED")
            _set(ws, "O", 2, "S1"); _set(ws, "P", 2, "M" + sname[-2:]); _set(ws, "Q", 2, "-F1", text=True)
            _set(ws, "R", 2, "A")
        wb.save(path)

    with tempfile.TemporaryDirectory() as d:
        io = os.path.join(d, "io.xlsx"); out = os.path.join(d, "out"); build(io)
        params = config.load_params()
        params["io_list"] = {"path": io, "sheet": r"NET SAFETY \d{1,3}/gmi", "header_row": 1}
        params["output_dir"] = out
        res = pop.populate(params, out_dir=out, emit=lambda *_: None)
        eq(res.processed, 2, "rows from BOTH matching sheets")
        eq(sorted(res.sheets), ["NET SAFETY 50", "NET SAFETY 51"])
        ok("COVER" in res.skipped_sheets, "non-matching COVER logged as skipped")
        eq(sorted(r.index for r in res.results), ["0001", "0002"], "index is GLOBAL across sheets")
        # two distinct node cabinets, global numbering 000/001
        eq(sorted(r.diag_cabinet for r in res.results), ["000", "001"])


def test_idempotent_rerun():
    def check(params, out, d):
        r1 = pop.populate(params, out_dir=out, emit=lambda *_: None)
        r2 = pop.populate(params, out_dir=out, emit=lambda *_: None)
        eq(r1.indexed, r2.indexed, "re-run does not double-index")
        eq(_by_addr(r2.results, "I2.0").index, "0001", "index stable across re-run")
    _run(check)


def test_fills_source_in_place_and_backs_up():
    def check(params, out, d):
        io = params["io_list"]["path"]
        baks = lambda: [f for f in os.listdir(d) if ".bak_" in f]
        r1 = pop.populate(params, out_dir=out, emit=lambda *_: None)
        eq(r1.output_path, io, "the SOURCE is filled in place (it becomes the populated doc)")
        ok(r1.backup and os.path.exists(r1.backup), "a changing fill keeps a timestamped backup")
        eq(len(baks()), 1, "exactly one backup after the changing run")
        r2 = pop.populate(params, out_dir=out, emit=lambda *_: None)
        eq(r2.backup, "", "a no-op re-fill removes its own backup")
        eq(len(baks()), 1, "the no-op run leaves no new backup")
    _run(check)


if __name__ == "__main__":
    raise SystemExit(run("iolist_diag", [
        ("populates_and_skips_nodemeta", test_populates_and_skips_nodemeta),
        ("script_type_and_index", test_script_type_and_index),
        ("diag_allocation", test_diag_allocation),
        ("writes_columns_and_diagblocks", test_writes_columns_and_diagblocks),
        ("fire_alarm_rung", test_fire_alarm_rung),
        ("ladder_yields_canonical_directly", test_ladder_yields_canonical_directly),
        ("strike_handling", test_strike_handling),
        ("multi_sheet_global_and_skip_log", test_multi_sheet_global_and_skip_log),
        ("idempotent_rerun", test_idempotent_rerun),
        ("fills_source_in_place_and_backs_up", test_fills_source_in_place_and_backs_up),
    ]))
