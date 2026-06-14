#!/usr/bin/env python3
"""Generate per-machine interface I/O tables from the I/O List.

A row whose Script Type equals the trigger type "IOC" marks a machine
interface; its Index (format MACHINETYPE-nn, e.g. SORTER-01) names the
instance. For each such instance the interface I/O table template is copied to
  <output>/IF_<instance>.xlsx
and the title filled with the source device + IP. An existing target file is
PRESERVED (so hand-added rows survive a re-run).

Interface table columns - the engineer fills the first four by hand, the last
two derive by Excel formula:
  Signal Mnemonic | Other Side Address (shared) | PLC Tag Name |
  PLC Logic (0=as-is, 1=inverted) | TIA IO Tag | IO Mapping SCL

Strikethrough source rows mean "predisposition, not used" and are skipped.

Usage:
  python interface_tool.py <io_list.xlsx> [--sheet "NET SAFETY 50"]
         [--header-row 1] [--out <dir>] [--template <xlsx>]
"""
from __future__ import annotations
import argparse
import os
import shutil
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font

TRIGGER_TYPE = "IOC"

# interface table layout (header row 2; title row 1; data from row 3)
COLUMNS = [
    "Signal Mnemonic",
    "Other Side Address (shared)",
    "PLC Tag Name",
    "PLC Logic (0=as-is,1=inverted)",
    "TIA IO Tag",
    "IO Mapping SCL",
]
DATA_START_ROW = 3
TEMPLATE_ROWS = 60  # pre-formula'd rows ready for hand data


def build_template(path: str) -> None:
    """Creates the interface I/O table template workbook (idempotent caller checks existence)."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "Interface"
    ws["A1"] = "INTERFACE I/O TABLE - {INSTANCE}"
    for c, name in enumerate(COLUMNS, 1):
        ws.cell(row=2, column=c, value=name)
    # derived columns: E = TIA IO Tag (= PLC tag name), F = IO Mapping SCL
    for r in range(DATA_START_ROW, DATA_START_ROW + TEMPLATE_ROWS):
        ws.cell(row=r, column=5,
                value=f'=IF($C{r}="","",$C{r})')
        ws.cell(row=r, column=6,
                value=f'=IF($C{r}="","",$C{r}&" := "&IF($D{r}=1,"NOT ","")&$B{r}&";")')
    for c in range(1, len(COLUMNS) + 1):
        ws.cell(row=2, column=c).font = Font(bold=True)
        ws.column_dimensions[ws.cell(row=2, column=c).column_letter].width = 26
    wb.save(path)


def _header_index(ws, header_row: int) -> dict:
    return {
        str(cell.value).strip(): cell.column
        for cell in ws[header_row]
        if cell.value not in (None, "")
    }


def _row_struck(ws, row_index: int, last_col: int) -> bool:
    for c in range(1, last_col + 1):
        cell = ws.cell(row=row_index, column=c)
        if cell.value not in (None, "") and cell.font and cell.font.strike:
            return True
    return False


def find_interfaces(io_path: str, sheet: str, header_row: int) -> list[dict]:
    """Returns one record per IOC row: {instance, device, ip, source_row}."""
    wb = load_workbook(io_path, data_only=True)  # not read_only: need font.strike
    ws = wb[sheet]
    cols = _header_index(ws, header_row)
    for required in ("Script Type", "Index"):
        if required not in cols:
            raise SystemExit(f"column '{required}' not found in sheet '{sheet}' header row {header_row}")
    script_c = cols["Script Type"]
    index_c = cols["Index"]
    device_c = cols.get("Device")
    ip_c = cols.get("Profinet IP")
    last_col = ws.max_column

    interfaces = []
    for r in range(header_row + 1, ws.max_row + 1):
        script = ws.cell(row=r, column=script_c).value
        if script is None or str(script).strip().upper() != TRIGGER_TYPE:
            continue
        if _row_struck(ws, r, last_col):
            continue
        instance = str(ws.cell(row=r, column=index_c).value or "").strip()
        if not instance:
            print(f"  WARNING: IOC row {r} has no Index - skipped")
            continue
        interfaces.append({
            "instance": instance,
            "device": str(ws.cell(row=r, column=device_c).value or "").strip() if device_c else "",
            "ip": str(ws.cell(row=r, column=ip_c).value or "").strip() if ip_c else "",
            "source_row": r,
        })
    wb.close()
    return interfaces


def _safe_name(instance: str) -> str:
    bad = '\\/:*?"<>|'
    return "".join("_" if ch in bad else ch for ch in instance)


def generate(io_path: str, sheet: str, header_row: int, out_dir: str, template_path: str) -> int:
    if not os.path.exists(template_path):
        build_template(template_path)
        print(f"  created interface template: {template_path}")
    os.makedirs(out_dir, exist_ok=True)

    interfaces = find_interfaces(io_path, sheet, header_row)
    if not interfaces:
        print("  no IOC interface rows found")
        return 0

    created = 0
    for itf in interfaces:
        target = os.path.join(out_dir, f"IF_{_safe_name(itf['instance'])}.xlsx")
        if os.path.exists(target):
            print(f"  preserved (exists): {os.path.basename(target)}")
            continue
        shutil.copyfile(template_path, target)
        wb = load_workbook(target)
        ws = wb.active
        ws.title = _safe_name(itf["instance"])[:31]
        ws["A1"] = (f"INTERFACE I/O TABLE - {itf['instance']}"
                    f"   (source {itf['device']} @ {itf['ip']})")
        wb.save(target)
        wb.close()
        created += 1
        print(f"  created: {os.path.basename(target)}  <- IOC row {itf['source_row']} ({itf['device']})")
    return created


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate interface I/O tables from IOC rows of the I/O List")
    ap.add_argument("io_list")
    ap.add_argument("--sheet", default="NET SAFETY 50")
    ap.add_argument("--header-row", type=int, default=1)
    ap.add_argument("--out", default="Output/Interfaces")
    ap.add_argument("--template", default="Templates/Interface_IO_Template.xlsx")
    args = ap.parse_args()

    print(f"interface generation from {args.io_list} [{args.sheet}]")
    n = generate(args.io_list, args.sheet, args.header_row, args.out, args.template)
    print(f"done: {n} interface table(s) created, others preserved")


if __name__ == "__main__":
    main()
