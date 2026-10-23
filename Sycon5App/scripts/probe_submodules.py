"""Probe - the Modules grid's submodule rows of an AL1202 (nothing saved): open the dialog of the station, the
Modules page, expand its `8 Ports` row, press Add Submodule, and report what the grid shows (the text bands of
its rows) and which in-place editors (ctrl ids >= 1900, their items) open on the Subslot (x+60) and Submodule
(x+150) cells of the rows under it; then Cancel / No. Attaches to a running SYCON.net whose project holds the
station, else launches the smoke project.

Usage:  ..\\.venv\\Scripts\\python -I scripts\\probe_submodules.py [--project <spj>] [--station <name>]
            [--module-row 2] [--rows 3 4 5]
"""
import argparse
import os
import sys
import time

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP)
from pywinauto import mouse  # noqa: E402

from sycon5 import SyconDriver  # noqa: E402
from sycon5.device import MODULE_X, MODULES_GRID_ID, ROW_H, SLOT_X, DeviceDialog, row_y  # noqa: E402
from sycon5.drawing import text_bands  # noqa: E402
from sycon5.session import log  # noqa: E402

SMOKE = os.path.join(APP, "spike", "scratch", "FVT_LowerSorter_smoke", "Smoke.spj")


def bands(dlg):
    r = dlg.pane(MODULES_GRID_ID).rectangle()
    return [(y, n) for y, n in text_bands(r, ROW_H) if n]


def editors(dlg):
    out = []
    for c in dlg.controls():
        kind = c.class_name()
        text = c.selected_text() if kind == "ComboBox" else c.window_text()
        items = c.item_texts() if kind == "ComboBox" else None
        out.append((kind, c.control_id(), tuple(c.rectangle()), text, items))
    return out


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--project", default=SMOKE)
    p.add_argument("--station", default="n0035-trib-sm006-k1")
    p.add_argument("--module-row", type=int, default=2, help="the module row to expand (1 = DAP)")
    p.add_argument("--rows", type=int, nargs="+", default=[3, 4, 5], help="the rows whose cells are probed")
    a = p.parse_args(argv)
    d = SyconDriver()
    launched = not d.session.attach_if_running()
    d.open(a.project)
    dlg = DeviceDialog(d.session, a.station)
    try:
        r = dlg.modules_page()
        log("grid:", r, "| slots used:", dlg.slots_used(), "| data length:", dlg.texts("State of data length"))
        log("bands before:", bands(dlg))
        dlg.expand_row(a.module_row)
        log("bands after expanding row %d:" % a.module_row, bands(dlg))
        dlg.select_row(a.module_row)
        dlg.press("Add Submodule", settle=2.0)
        log("errors after Add Submodule:", d.session.dismiss_errors())
        log("bands after Add Submodule:", bands(dlg), "| data length:", dlg.texts("State of data length"))
        for row in a.rows:
            for name, x in (("subslot", SLOT_X), ("submodule", MODULE_X)):
                mouse.click(coords=(r.left + x, r.top + row_y(row)))
                time.sleep(1.2)
                log("row %d %s cell:" % (row, name), editors(dlg))
                dlg._close_dropdowns()
                time.sleep(0.4)
        log("bands at the end:", bands(dlg))
    finally:
        if dlg.is_open():
            dlg.close(keep=False)
        if launched:
            d.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
