"""Staging (domain.identity + domain.staging): the FLD/tag identity + the IoList read into rows."""
import os
import tempfile

from openpyxl import Workbook
from openpyxl.styles import Font

from _harness import run, eq, ok
from pipeline4.domain import identity, staging
from pipeline4.io import workbook


def test_identity_flds_and_tag():
    row = {"functional_unit": "S1", "location": "+SG1", "device": "-B1", "script_type": "DI1/2", "bit": "I0.0",
           "type": {"category": "Safety", "tag_name": "Door [ {combined_FLD} ]", "tagtable_name": "SAFETY_Doors"}}
    row["combined_FLD"] = identity.combined_fld(row)
    eq(identity.fld(row), "S1+SG1-B1", "iol_FLD = FU+LOC+DEV")
    eq(identity.combined_fld(row), "S1+SG1-B1", "combined == iol when there is no C&E FLD")
    ok(identity.is_io_signal(row), "an I/Q bit on a non-interface type is an I/O signal")
    eq(identity.tag_name(row), "Door [ S1+SG1-B1 ]", "tag_name template interpolated")
    eq(identity.tagtable(row), "SAFETY_Doors", "tagtable from the type")


def test_combined_fld_appends_ce_when_different():
    row = {"functional_unit": "S1", "location": "+SG1", "device": "-B1",
           "ce_functional_unit": "S1", "ce_location": "+CE", "ce_device": "-B1"}
    eq(identity.combined_fld(row), "S1+SG1-B1 S1+CE-B1", "the C&E-side FLD is appended only when it differs")


_COLMAP = [{"column": c, "canonical": n} for c, n in
           [("A", "functional_unit"), ("B", "location"), ("C", "device"),
            ("D", "script_type"), ("E", "bit"), ("F", "skip_reason")]]
_TYPES = {"DI1/2": {"type_id": "DI1/2", "category": "Safety",
                    "tag_name": "Door [ {combined_FLD} ]", "tagtable_name": "SAFETY_Doors"}}


def _iolist(path):
    wb = Workbook()
    ws = wb.active
    ws.title = "NET SAFETY 50"
    for col, head in zip("ABCDEF", ["FU", "Loc", "Dev", "Type", "Bit", "Skip"]):
        ws[f"{col}1"] = head
    ws["A2"] = "S1"; ws["B2"] = "+SG1"; ws["C2"] = "-B1"; ws["D2"] = "DI1/2"; ws["E2"] = "I0.0"
    ws["A3"] = "S2"; ws["B3"] = "+SG2"; ws["C3"] = "-B2"; ws["D3"] = "DI1/2"; ws["E3"] = "I0.1"; ws["F3"] = "skip me"
    ws["A4"] = "S3"; ws["B4"] = "+SG3"; ws["C4"] = "-B3"; ws["D4"] = "DI1/2"; ws["E4"] = "I0.2"
    ws["A4"].font = Font(strike=True)
    wb.save(path)


def test_read_view_drops_skip_and_struck():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "io.xlsx"); _iolist(p)
        v = workbook.open_sheet(p, "NET SAFETY 50", 1)
        rows = staging._read_view(v, _COLMAP, True, _TYPES)        # strike_exclude=True
        eq(len(rows), 1, "the Skip-Reason row + the struck row are dropped -> 1 kept")
        r = rows[0]
        eq(r["functional_unit"], "S1"); eq(r["script_type"], "DI1/2")
        eq(r["type"]["type_id"], "DI1/2", "the resolved type is attached")
        eq(r["source_sheet"], "NET SAFETY 50"); eq(r["source_row"], 2)
        v.close()


def test_read_view_keeps_struck_when_not_excluding():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "io.xlsx"); _iolist(p)
        v = workbook.open_sheet(p, "NET SAFETY 50", 1)
        rows = staging._read_view(v, _COLMAP, False, _TYPES)       # strike_exclude=False
        eq(len(rows), 2, "the struck row is KEPT when not excluding; the Skip-Reason row is still dropped")
        v.close()


if __name__ == "__main__":
    import sys
    sys.exit(run("staging", [
        ("identity_flds_and_tag", test_identity_flds_and_tag),
        ("combined_fld_appends_ce_when_different", test_combined_fld_appends_ce_when_different),
        ("read_view_drops_skip_and_struck", test_read_view_drops_skip_and_struck),
        ("read_view_keeps_struck_when_not_excluding", test_read_view_keeps_struck_when_not_excluding),
    ]))
