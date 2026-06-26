"""Phase 400c - the IF_*.xlsx projection (domain.interface_xlsx): the custom-block writer + helpers."""
from openpyxl import Workbook
from openpyxl.worksheet.table import Table as XlTable

from _harness import run, eq, ok
from pipeline4.domain import interface_xlsx


def test_coerce_int_and_safe_name():
    eq(interface_xlsx._coerce_int("10"), 10)
    eq(interface_xlsx._coerce_int("10.0"), 10, "a float-read int string coerces")
    eq(interface_xlsx._coerce_int(""), None)
    eq(interface_xlsx._coerce_int("None"), None, "a stringified None -> None (the WORD bit)")
    eq(interface_xlsx._safe_name('SORTER+DIAG-02'), "SORTER+DIAG-02")
    eq(interface_xlsx._safe_name('A/B:C'), "A_B_C", "filesystem-unsafe chars replaced")


def _synthetic_sheet():
    wb = Workbook()
    ws = wb.active
    headers = ["Category", "Data Type", "Direction </>", "I/O Offset Byte", "I/O Bit",
               "Signal Name Side 1", "Expression Side 1"]
    for c, h in enumerate(headers, start=1):
        ws.cell(1, c, h)
    ws.cell(2, 1, "TEMPLATE"); ws.cell(2, 3, ">"); ws.cell(2, 4, 0)     # one template data row
    ws.add_table(XlTable(displayName="T", ref="A1:G2"))
    return wb, ws


def _col(ws, header):
    return {str(ws.cell(1, c).value).strip(): c for c in range(1, ws.max_column + 1)}[header]


def test_append_custom_rows_bool_block_and_padding():
    wb, ws = _synthetic_sheet()
    elems = [{"category": "X", "direction": "Q", "data_type": "BOOL", "offset_byte": 10, "bit": 0,
              "signal_name": "PNC_a", "expression": '"DB"."a"'},
             {"category": "X", "direction": "Q", "data_type": "BOOL", "offset_byte": 10, "bit": 1,
              "signal_name": "PNC_b", "expression": '"DB"."b"'}]
    interface_xlsx._append_custom_rows(ws, elems)
    cat, off, bit, s1, e1 = (_col(ws, "Category"), _col(ws, "I/O Offset Byte"), _col(ws, "I/O Bit"),
                             _col(ws, "Signal Name Side 1"), _col(ws, "Expression Side 1"))
    # the 2 real signals on rows 3-4 (low bits of byte 10), then 14 blank padding rows -> a full 2-byte block
    eq((ws.cell(3, cat).value, ws.cell(3, off).value, ws.cell(3, bit).value), ("X", 10, 0))
    eq((ws.cell(3, s1).value, ws.cell(3, e1).value), ("PNC_a", '"DB"."a"'))
    eq((ws.cell(4, off).value, ws.cell(4, bit).value), (10, 1), "second signal, bit 1")
    eq(ws.cell(5, e1).value in (None, ""), True, "row 5 is blank padding (addressed, no signal)")
    eq((ws.cell(18, cat).value, ws.cell(18, off).value, ws.cell(18, bit).value), ("X", 11, 7),
       "the block runs a full 16 bits (byte 10 + 11), last padding row at 11.7")
    eq(ws.tables["T"].ref, "A1:G18", "the table ref extends to the last written row")


def test_append_custom_rows_word_row_and_separator():
    wb, ws = _synthetic_sheet()
    elems = [{"category": "SPD", "direction": "Q", "data_type": "WORD", "offset_byte": 12, "bit": None,
              "signal_name": "PNC_speed", "expression": '"DB"."speed"'}]
    interface_xlsx._append_custom_rows(ws, elems)
    dt, off, bit = _col(ws, "Data Type"), _col(ws, "I/O Offset Byte"), _col(ws, "I/O Bit")
    eq((ws.cell(3, dt).value, ws.cell(3, off).value, ws.cell(3, bit).value), ("WORD", 12, None),
       "a WORD is one row, even byte, no bit")
    ok(ws.tables["T"].ref in ("A1:G3", "A1:G4"), "one word row (+ a trailing separator)")


if __name__ == "__main__":
    import sys
    sys.exit(run("interface_xlsx", [
        ("coerce_int_and_safe_name", test_coerce_int_and_safe_name),
        ("append_custom_rows_bool_block_and_padding", test_append_custom_rows_bool_block_and_padding),
        ("append_custom_rows_word_row_and_separator", test_append_custom_rows_word_row_and_separator),
    ]))
