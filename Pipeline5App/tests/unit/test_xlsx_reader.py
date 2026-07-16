"""The shared workbook reader (io.workbook): positional access, header matching, strike, iteration."""
import os
import tempfile

from openpyxl import Workbook
from openpyxl.styles import Font

from _harness import run, eq, ok, raises
from pipeline5.documents import xlsx_reader as workbook


def _make_iolist(path):
    wb = Workbook()
    ws = wb.active
    ws.title = "NET SAFETY 50"
    ws["A1"] = "Functional\nUnit"          # a header that wraps across lines
    ws["B1"] = "Address (1 part)"
    ws["A2"] = "S1-MS1"; ws["B2"] = "I0.0"
    ws["A3"] = "S2-MS2"; ws["B3"] = "I0.1"
    ws["A3"].font = Font(strike=True)       # row 3 struck
    wb.save(path)


def test_open_sheets_matches_by_regex():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "iolist.xlsx")
        _make_iolist(path)
        views = workbook.open_sheets(path, "/NET SAFETY \\d+/", header_row=1)
        eq(len(views), 1, "one matching sheet")
        eq(views[0].name, "NET SAFETY 50")
        views[0].close()


def test_positional_access_and_header_match():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "iolist.xlsx")
        _make_iolist(path)
        v = workbook.open_sheet(path, "NET SAFETY 50", header_row=1)
        ok(v.header_matches("A", "Functional Unit"), "newline-normalized prefix match on the header")
        ok(v.header_matches("B", "Address"), "prefix match ignores the '(1 part)' suffix")
        ok(not v.header_matches("A", "Address"), "a non-matching header is rejected")
        eq(v.text(2, "A"), "S1-MS1", "by-letter access")
        eq(v.text(2, 2), "I0.0", "by-1-based-int access")
        eq(v.text(99, "A"), "", "an empty cell -> ''")
        eq(v.location(2, "A"), "NET SAFETY 50!A2", "clickable sheet!cell (no workbook name)")
        v.close()


def test_data_rows_and_strike():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "iolist.xlsx")
        _make_iolist(path)
        v = workbook.open_sheet(path, "NET SAFETY 50", header_row=1)
        eq(list(v.data_rows()), [2, 3], "rows from first_data_row..max_row")
        ok(v.row_struck(3), "the struck row is detected")
        ok(not v.row_struck(2), "a normal row is not struck")
        v.close()


def test_no_matching_sheet_raises():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "iolist.xlsx")
        _make_iolist(path)
        raises(ValueError, lambda: workbook.open_sheet(path, "/DOES NOT EXIST/"))


if __name__ == "__main__":
    import sys
    sys.exit(run("workbook", [
        ("open_sheets_matches_by_regex", test_open_sheets_matches_by_regex),
        ("positional_access_and_header_match", test_positional_access_and_header_match),
        ("data_rows_and_strike", test_data_rows_and_strike),
        ("no_matching_sheet_raises", test_no_matching_sheet_raises),
    ]))
