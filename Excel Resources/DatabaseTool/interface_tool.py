#!/usr/bin/env python3
"""Generate per-machine interface I/O tables from the I/O List.

A row whose Script Type equals the trigger type "IOC" marks a machine
interface; its Index (format MACHINETYPE-nn, e.g. SORTER-01) names the
instance. For each such instance the interface I/O table template is copied to
  <output>/IF_<instance>.xlsx
and the title filled with the source device + IP. An existing target file is
PRESERVED (so hand-added rows survive a re-run).

The template is copied verbatim and PLACEHOLDER TOKENS are substituted per
instance, so the template can be authored by hand in Excel and owns its own
columns/formatting/formulas. Tokens replaced anywhere in the sheet:
  {INSTANCE}  e.g. SORTER-01            {DEVICE}  source device, e.g. -K66201
  {BASE}      I/Q start byte (col G)    {IP}      source Profinet IP
  {SOURCEROW} source row number
Address formulas in the template reference the cell that held {BASE}; the
PLC address is "%I<BASE+offset>[.bit]" / "%Q..." (column G of the IOC row is
the start byte for both the I and Q areas of that interface).

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

# Provisional template columns (the user's hand-authored template replaces this).
# Engineer fills Direction..PLC Logic by hand; PLC Address / TIA IO Tag / SCL derive.
COLUMNS = [
    "Direction (I/Q)",
    "Data Type",
    "Offset (bytes from base)",
    "Bit",
    "Signal Mnemonic",
    "Other Side Address (shared)",
    "PLC Tag Name",
    "PLC Logic (0=as-is,1=inverted)",
    "PLC Address",
    "TIA IO Tag",
    "IO Mapping SCL",
]
HEADER_ROW = 3
DATA_START_ROW = 4
TEMPLATE_ROWS = 60
BASE_CELL = "B2"      # holds {BASE}
BASE_REF = "$B$2"     # absolute ref used in formulas (survives copy-down)


def build_template(path: str) -> None:
    """Provisional interface I/O table template (regenerated only when missing).
    Uses {INSTANCE}/{BASE}/{DEVICE}/{IP} tokens the generator substitutes."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "Interface"
    ws["A1"] = "INTERFACE I/O TABLE - {INSTANCE}   (source {DEVICE} @ {IP})"
    ws["A2"] = "Base Address (I/Q start byte):"
    ws[BASE_CELL] = "{BASE}"
    for c, name in enumerate(COLUMNS, 1):
        ws.cell(row=HEADER_ROW, column=c, value=name).font = Font(bold=True)
    # columns: A Dir, B DataType, C Offset, D Bit, E Mnemonic, F OtherAddr,
    #          G PlcTag, H Logic, I PlcAddress, J TiaTag, K SCL
    for r in range(DATA_START_ROW, DATA_START_ROW + TEMPLATE_ROWS):
        # PLC Address: %<dir>[<B|W|D>]<base+offset>[.bit]  (no size letter for Bool)
        ws.cell(row=r, column=9, value=(
            f'=IF($G{r}="","","%"&$A{r}'
            f'&IF($B{r}="Bool","",UPPER(LEFT($B{r},1)))'
            f'&({BASE_REF}+N($C{r}))'
            f'&IF($B{r}="Bool","."&$D{r},""))'))
        # TIA IO Tag (provisional = PLC tag name)
        ws.cell(row=r, column=10, value=f'=IF($G{r}="","",$G{r})')
        # IO Mapping SCL: PlcTag := [NOT] OtherSide;
        ws.cell(row=r, column=11,
                value=f'=IF($G{r}="","",$G{r}&" := "&IF($H{r}=1,"NOT ","")&$F{r}&";")')
    for c in range(1, len(COLUMNS) + 1):
        ws.column_dimensions[ws.cell(row=HEADER_ROW, column=c).column_letter].width = 24
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
    """Returns one record per IOC row: {instance, base, device, ip, source_row}.
    base = the I/Q start byte from the 'Bit' column (col G of the IOC row)."""
    wb = load_workbook(io_path, data_only=True)  # not read_only: need font.strike
    ws = wb[sheet]
    cols = _header_index(ws, header_row)
    for required in ("Script Type", "Index"):
        if required not in cols:
            raise SystemExit(f"column '{required}' not found in sheet '{sheet}' header row {header_row}")
    script_c = cols["Script Type"]
    index_c = cols["Index"]
    bit_c = cols.get("Bit")
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
            "base": str(ws.cell(row=r, column=bit_c).value or "").strip() if bit_c else "",
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
        _fill_tokens(target, itf)
        created += 1
        print(f"  created: {os.path.basename(target)}  <- IOC row {itf['source_row']} "
              f"({itf['device']}, base {itf['base'] or '?'})")
    return created


def _fill_tokens(target: str, itf: dict) -> None:
    """Substitutes {INSTANCE}/{BASE}/{DEVICE}/{IP}/{SOURCEROW} tokens anywhere in
    the sheet. {BASE} becomes a number when possible so address formulas compute."""
    tokens = {
        "{INSTANCE}": itf["instance"],
        "{DEVICE}": itf["device"],
        "{IP}": itf["ip"],
        "{SOURCEROW}": str(itf["source_row"]),
    }
    base_num = None
    try:
        base_num = int(str(itf["base"]).strip())
    except (ValueError, TypeError):
        pass

    wb = load_workbook(target)
    ws = wb.active
    ws.title = _safe_name(itf["instance"])[:31]
    for row in ws.iter_rows():
        for cell in row:
            if not isinstance(cell.value, str):
                continue
            if cell.value == "{BASE}":
                cell.value = base_num if base_num is not None else itf["base"]
                continue
            new = cell.value
            for token, value in tokens.items():
                if token in new:
                    new = new.replace(token, value)
            if new != cell.value:
                cell.value = new
    wb.save(target)
    wb.close()


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
