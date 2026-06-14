#!/usr/bin/env python3
"""Synthetic test for the C&E/AREA -> I/O List cross-validation: covers match,
missing device, address mismatch, and AREA sheets. Run: python test_validation.py
"""
import os
import tempfile
from openpyxl import Workbook

from safetydb import validation

failures = 0


def check(name, ok, detail=""):
    global failures
    print(("PASS  " if ok else "FAIL  ") + name + (f"  [{detail}]" if detail else ""))
    if not ok:
        failures += 1


def _text(ws, cell, value):
    """Write a literal string; '=' values would otherwise become formulas
    (the real document stores these tags as text)."""
    ws[cell] = value
    if isinstance(value, str) and value.startswith("="):
        ws[cell].data_type = "s"


def make_ce(path):
    wb = Workbook()
    m = wb.active
    m.title = "CAUSE&EFFECT MATRIX"
    # header row 2: F=BIT, J=FUNCTIONAL UNIT, K=LOCATION, L=DEVICE
    m["F2"], m["J2"], m["K2"], m["L2"] = "BIT (ADDRESS)", "FUNCTIONAL UNIT", "LOCATION", "DEVICE"
    # data from row 5
    rows = [
        ("I20.0", "=S1", "+MS1.CC1", "-S67001"),   # match
        ("I20.9", "=S1", "+MS1.CC1", "-S67001"),   # device ok, address mismatch
        ("I120.0", "=S1", "+SG1", "-B1"),          # device missing
    ]
    for i, (addr, fu, loc, dev) in enumerate(rows, start=5):
        m[f"F{i}"] = addr
        _text(m, f"J{i}", fu)
        _text(m, f"K{i}", loc)
        _text(m, f"L{i}", dev)

    a = wb.create_sheet("AREA 1")
    a["A3"], a["C3"] = "SIGLA CONTATTORE", "DIGITAL OUTPUT"  # header row 3
    _text(a, "A4", "=S1+PC1.CC1-K65060")                     # data row 4 - missing
    a["C4"] = "Q130.0"
    wb.save(path)


def main():
    tmp = tempfile.mkdtemp(prefix="valtest_")
    ce_path = os.path.join(tmp, "ce.xlsx")
    make_ce(ce_path)

    io_rows = [
        {"functional_unit": "=S1", "location": "+MS1.CC1", "device": "-S67001", "bit": "I20.0"},
        {"functional_unit": "=S1", "location": "+MS1.CC1", "device": "-S67002", "bit": "I20.2"},
    ]
    params = {"ce": {"path": ce_path, "matrix_sheet": "CAUSE&EFFECT MATRIX",
                     "matrix_header_row": 2, "matrix_data_row": 5,
                     "area_header_row": 3, "area_data_row": 4}}

    log = validation.validate(params, io_rows)
    for e in log:
        print("   " + e.format())

    def find(loc):
        return next((e for e in log if e.location == loc), None)

    check("F5 device+address match -> PASS", find("CAUSE&EFFECT MATRIX!F5").level == "PASS")
    e = find("CAUSE&EFFECT MATRIX!F6")
    check("F6 address mismatch -> FAIL", e.level == "FAIL" and "mismatch" in e.message)
    e = find("CAUSE&EFFECT MATRIX!F7")
    check("F7 missing device -> FAIL", e.level == "FAIL" and "not found" in e.message)
    e = find("AREA 1!C4")
    check("AREA 1 C4 checked with cell address -> FAIL", e is not None and e.level == "FAIL")
    check("log includes passes and fails", any(x.level == "PASS" for x in log) and any(x.level == "FAIL" for x in log))

    print("ALL CHECKS PASS" if failures == 0 else f"{failures} CHECK(S) FAILED")
    raise SystemExit(0 if failures == 0 else 1)


if __name__ == "__main__":
    main()
