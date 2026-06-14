"""Validation: cross-check the C&E matrix and AREA sheets against the I/O List.

Match key = FUNCTIONAL UNIT + LOCATION + DEVICE; address = the Bit/address cell.
  I/O List : functional_unit (O) + location (P) + device (Q), address = bit (G)
  C&E      : J + K + L,                              address = F
  AREA n   : column A (already concatenated),        address = column C
Every C&E / AREA reference must exist in the I/O List with a matching address.
Only the CAUSE&EFFECT MATRIX and AREA n sheets are checked - all other sheets
are ignored. Every check is logged (pass AND fail) with its cell addresses.
"""
from __future__ import annotations
import os
from openpyxl import load_workbook
from openpyxl.utils import column_index_from_string, get_column_letter

from . import config


class LogEntry:
    __slots__ = ("level", "location", "key", "address", "message")

    def __init__(self, level, location, key, address, message):
        self.level = level          # PASS / FAIL / INFO
        self.location = location    # "Sheet!Cell"
        self.key = key
        self.address = address
        self.message = message

    def format(self) -> str:
        head = f"[{self.level:4}] {self.location}"
        body = f"key='{self.key}' addr='{self.address}'"
        return f"{head}  {body}  {self.message}".rstrip()


def _norm(value) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _key(*parts) -> str:
    """Device key: concatenated, whitespace removed, upper-cased."""
    return "".join(_norm(p) for p in parts).replace(" ", "").upper()


def _addr(value) -> str:
    return _norm(value).replace(" ", "").upper()


def build_io_index(io_rows: list) -> dict:
    """key -> set of addresses found in the I/O List (only rows with a key)."""
    index: dict[str, set] = {}
    for r in io_rows:
        key = _key(r.get("functional_unit"), r.get("location"), r.get("device"))
        if key in ("", None):
            continue
        index.setdefault(key, set()).add(_addr(r.get("bit")))
    return index


def _check_reference(sheet, row, key_cells, key, addr_cell, address, io_index, log):
    """One C&E/AREA reference vs the I/O List; appends a PASS or FAIL entry."""
    location = f"{sheet}!{addr_cell}"
    keyloc = f"(key {key_cells})"
    if not key:
        log.append(LogEntry("FAIL", location, key, address, f"empty device key {keyloc}"))
        return
    addrs = io_index.get(key)
    if addrs is None:
        log.append(LogEntry("FAIL", location, key, address,
                            f"device {keyloc} not found in I/O List"))
    elif address not in addrs:
        log.append(LogEntry("FAIL", location, key, address,
                            f"device found {keyloc} but address mismatch; I/O List has {sorted(addrs)}"))
    else:
        log.append(LogEntry("PASS", location, key, address, f"matches I/O List {keyloc}"))


def check_ce_matrix(params: dict, io_index: dict, log: list) -> None:
    spec = params["ce"]
    cols = {m["canonical"]: m["column"] for m in config.load_column_map("CE")}
    wb = load_workbook(spec["path"], data_only=True, read_only=True)
    sheet = spec["matrix_sheet"]
    if sheet not in wb.sheetnames:
        log.append(LogEntry("INFO", sheet, "", "", "sheet not found - skipped"))
        wb.close()
        return
    ws = wb[sheet]
    fu_c = column_index_from_string(cols["functional_unit"])
    loc_c = column_index_from_string(cols["location"])
    dev_c = column_index_from_string(cols["device"])
    addr_c = column_index_from_string(cols["address"])

    checked = 0
    for r in range(spec["matrix_data_row"], ws.max_row + 1):
        fu = ws.cell(r, fu_c).value
        loc = ws.cell(r, loc_c).value
        dev = ws.cell(r, dev_c).value
        address = _addr(ws.cell(r, addr_c).value)
        if not any(_norm(v) for v in (fu, loc, dev)) and not address:
            continue  # empty row
        key = _key(fu, loc, dev)
        key_cells = f"{cols['functional_unit']}{r}:{cols['device']}{r}"
        _check_reference(sheet, r, key_cells, key, f"{cols['address']}{r}", address, io_index, log)
        checked += 1
    wb.close()
    log.append(LogEntry("INFO", sheet, "", "", f"{checked} reference(s) checked"))


def check_area_sheets(params: dict, io_index: dict, log: list) -> None:
    spec = params["ce"]
    cols = {m["canonical"]: m["column"] for m in config.load_column_map("AREA")}
    wb = load_workbook(spec["path"], data_only=True, read_only=True)
    key_c = column_index_from_string(cols["concat_id"])
    addr_c = column_index_from_string(cols["address"])

    area_sheets = [s for s in wb.sheetnames if s.strip().upper().startswith("AREA")
                   and any(ch.isdigit() for ch in s)]
    for sheet in area_sheets:
        ws = wb[sheet]
        checked = 0
        for r in range(spec["area_data_row"], ws.max_row + 1):
            raw_key = ws.cell(r, key_c).value
            address = _addr(ws.cell(r, addr_c).value)
            if not _norm(raw_key) and not address:
                continue
            key = _key(raw_key)
            _check_reference(sheet, r, f"{cols['concat_id']}{r}", key,
                             f"{cols['address']}{r}", address, io_index, log)
            checked += 1
        log.append(LogEntry("INFO", sheet, "", "", f"{checked} reference(s) checked"))
    wb.close()


def validate(params: dict, io_rows: list) -> list:
    io_index = build_io_index(io_rows)
    log: list[LogEntry] = []
    log.append(LogEntry("INFO", "I/O List", "", "", f"{len(io_index)} distinct device key(s) indexed"))
    check_ce_matrix(params, io_index, log)
    check_area_sheets(params, io_index, log)
    return log


def write_log(log: list, out_dir: str) -> tuple[int, int]:
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "validation_log.txt")
    passed = sum(1 for e in log if e.level == "PASS")
    failed = sum(1 for e in log if e.level == "FAIL")
    with open(path, "w", encoding="utf-8") as f:
        for e in log:
            f.write(e.format() + "\n")
        f.write(f"\nSUMMARY: {passed} passed, {failed} failed\n")
    return passed, failed
