#!/usr/bin/env python3
"""Self-contained test for interface_tool: builds synthetic I/O Lists, runs the
generator, and checks naming, columns, formulas, strikethrough exclusion,
multiple instances and preserve-on-rerun. Run: python test_interface_tool.py
"""
import os
import shutil
import tempfile
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font

import interface_tool as it

failures = 0


def check(name, ok):
    global failures
    print(("PASS  " if ok else "FAIL  ") + name)
    if not ok:
        failures += 1


def make_io_list(path, rows, struck_rows=()):
    """rows: list of dict with keys device, ip, bit, script, index. Header row 1."""
    wb = Workbook()
    ws = wb.active
    ws.title = "NET SAFETY 50"
    headers = ["Device", "Profinet IP", "Bit", "Script Type", "Index"]
    for c, h in enumerate(headers, 1):
        ws.cell(1, c, h)
    for i, row in enumerate(rows, start=2):
        ws.cell(i, 1, row["device"])
        ws.cell(i, 2, row["ip"])
        ws.cell(i, 3, row.get("bit", ""))
        ws.cell(i, 4, row["script"])
        ws.cell(i, 5, row["index"])
        if (i - 2) in struck_rows:
            for c in range(1, 6):
                ws.cell(i, c).font = Font(strike=True)
    wb.save(path)


def main():
    tmp = tempfile.mkdtemp(prefix="iftest_")
    try:
        io_path = os.path.join(tmp, "io.xlsx")
        out = os.path.join(tmp, "out")
        tpl = os.path.join(tmp, "tpl.xlsx")

        make_io_list(io_path, [
            {"device": "-K66201", "ip": "192.168.50.6", "bit": "10000", "script": "IOC", "index": "SORTER-01"},
            {"device": "-S31001", "ip": "", "bit": "I0.0", "script": "E1/2", "index": "0001"},  # not IOC
            {"device": "-K66202", "ip": "192.168.50.7", "bit": "20000", "script": "IOC", "index": "SORTER-02"},
            {"device": "-K66203", "ip": "192.168.50.8", "bit": "30000", "script": "IOC", "index": "PALLETIZER-01"},
            {"device": "-K69999", "ip": "192.168.50.9", "bit": "40000", "script": "IOC", "index": "GHOST-99"},  # struck
        ], struck_rows={4})

        n = it.generate(io_path, "NET SAFETY 50", 1, out, tpl)
        check("creates one file per non-struck IOC row", n == 3)

        files = sorted(os.listdir(out))
        check("instance names preserved (dash kept)",
              files == ["IF_PALLETIZER-01.xlsx", "IF_SORTER-01.xlsx", "IF_SORTER-02.xlsx"])
        check("struck IOC row excluded", "IF_GHOST-99.xlsx" not in files)

        wb = load_workbook(os.path.join(out, "IF_SORTER-01.xlsx"))
        ws = wb.active
        check("title tokens filled (instance + source)", "SORTER-01" in ws["A1"].value and "-K66201" in ws["A1"].value)
        check("base address substituted as number", ws[it.BASE_CELL].value == 10000)
        check("all columns present",
              [ws.cell(it.HEADER_ROW, c).value for c in range(1, len(it.COLUMNS) + 1)] == it.COLUMNS)
        addr_formula = str(ws.cell(it.DATA_START_ROW, 9).value)
        check("PLC address formula uses absolute base ref", it.BASE_REF in addr_formula and '"%"' in addr_formula)
        scl_formula = str(ws.cell(it.DATA_START_ROW, 11).value)
        check("SCL mapping formula present", ':= "' in scl_formula and 'NOT ' in scl_formula)
        check("no leftover tokens", "{" not in ws["A1"].value and "{" not in str(ws[it.BASE_CELL].value))
        wb.close()

        # preserve-on-rerun: mark a file, regenerate, ensure it is untouched
        marker = os.path.join(out, "IF_SORTER-01.xlsx")
        wb = load_workbook(marker)
        wb.active["A20"] = "HAND ADDED"
        wb.save(marker)
        wb.close()
        n2 = it.generate(io_path, "NET SAFETY 50", 1, out, tpl)
        check("rerun creates nothing (all preserved)", n2 == 0)
        wb = load_workbook(marker)
        check("hand-added data survives rerun", wb.active["A20"].value == "HAND ADDED")
        wb.close()

        print("ALL CHECKS PASS" if failures == 0 else f"{failures} CHECK(S) FAILED")
        raise SystemExit(0 if failures == 0 else 1)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
