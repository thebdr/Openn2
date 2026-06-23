"""M6 gate: phase-100 registration, profiles, the header runner + reports, and the file-locked seam."""
import os
import tempfile
from _harness import run, eq, ok
from openpyxl import Workbook
from openpyxl.utils import column_index_from_string as CI

import pipeline3.phases  # noqa: F401  (registers all phases)
from pipeline3.registry import registry
from pipeline3.context import PipelineContext
from pipeline3.phases import p100_validation
from pipeline3.domain.validation import iolist
from pipeline3.io import workbook as wbk
from pipeline3.io.workbook import FileLockedError


def _set(ws, col, row, val, text=False):
    c = ws.cell(row=row, column=CI(col), value=val)
    if text:
        c.data_type = "s"
    return c


def _make_iolist(path):
    wb = Workbook(); ws = wb.active; ws.title = "NET SAFETY 50"
    for col, hdr in (("C", "Part No."), ("F", "ID"), ("O", "Functional unit"),
                     ("P", "Location"), ("Q", "Device")):
        _set(ws, col, 1, hdr)
    _set(ws, "G", 2, "I0.0"); _set(ws, "O", 2, "=S1", text=True)
    _set(ws, "P", 2, "+M1", text=True); _set(ws, "Q", 2, "-D1", text=True)
    wb.save(path)


def _diag_rows():
    return [{"diag_cabinet": "3", "diag_bit": "5", "type_hw": "A", "_source_sheet": "NET SAFETY 50",
             "_source_row": 2, "source_cell": "NET SAFETY 50!O2", "functional_unit": "=S",
             "location": "+M", "device": "-D", "bit": "", "script_type": "A", "index": "",
             "desc_l1": "", "desc_l1b": "", "drawing": "", "_type": {"in_diagnosis": True}}]


def _ctx(d, profile):
    io = os.path.join(d, "io.xlsx"); _make_iolist(io)
    return PipelineContext(
        params={"io_list": {"path": io, "sheet": "NET SAFETY 50", "header_row": 1},
                "strike_handling": "ignore", "ce": {"path": ""}},
        out_root=os.path.join(d, "out"), rows=_diag_rows(), lang="en", profile=profile)


def test_registration_and_profiles():
    ph = registry().get(100)
    eq(ph.requires, (300,))
    eq([s.number for s in ph.sub_phases], [110, 120, 130, 140, 150])
    main = [p.number for p in registry().topo_order(target=100, profile="main")]
    eq(main[-1], 100)
    ok(main.index(300) < main.index(100), "300 runs before 100")
    eq([p.number for p in registry().topo_order(profile="designer")], [300, 100])


def test_header_runner_writes_both_reports():
    with tempfile.TemporaryDirectory() as d:
        ctx = _ctx(d, "main")
        res = p100_validation.run(ctx)
        ok("validation_report" in res.artifacts and "validation_errors" in res.artifacts)
        rep, err = res.artifacts["validation_report"], res.artifacts["validation_errors"]
        ok(os.path.exists(rep) and os.path.exists(err), "both report files written")
        ok(os.path.getsize(rep) > os.path.getsize(err), "complete report is longer than errors-only")
        # directive 2A: every builder FINDING carries a code-traceable type. (The phase-header's own
        # ctx.emit status lines are not findings - they carry phase 0 here, since run() is called
        # directly without the engine setting _current_phase.)
        for e in ctx.log:
            if e.level != "PHASE" and e.phase != 0:
                ok(e.type, f"finding without a type: {e!r}")
        ok(any(e.type.startswith("diag_") for e in ctx.log), "150 ran in the main profile")


def test_designer_skips_150():
    with tempfile.TemporaryDirectory() as d:
        ctx = _ctx(d, "designer")
        res = p100_validation.run(ctx)
        ok(not any(e.type.startswith("diag_") for e in ctx.log), "150 disabled in the designer profile")
        ok(any(e.type == "ce_absent" for e in ctx.log), "130/140 skip (C&E absent) still recorded")


def test_file_locked_surfaces_as_iolist_locked():
    with tempfile.TemporaryDirectory() as d:
        ctx = _ctx(d, "main")
        orig = wbk.open_sheets
        wbk.open_sheets = lambda *a, **k: (_ for _ in ()).throw(FileLockedError(ctx.io_list_path()))
        try:
            out = iolist.run_iolist(ctx)
        finally:
            wbk.open_sheets = orig
        eq([(x.type, x.level) for x in out], [("iolist_locked", "FAIL")])


if __name__ == "__main__":
    raise SystemExit(run("p100_phase", [
        ("registration_and_profiles", test_registration_and_profiles),
        ("header_runner_writes_both_reports", test_header_runner_writes_both_reports),
        ("designer_skips_150", test_designer_skips_150),
        ("file_locked_surfaces_as_iolist_locked", test_file_locked_surfaces_as_iolist_locked),
    ]))
