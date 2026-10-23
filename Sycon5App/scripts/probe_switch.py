"""Probe - a SCALANCE XC216-4C in a NEW project (nothing saved): the switch dragged from the catalog (the entry
whose info pane cites the GSDML of the database), its dialog opened maximized, the DAP row expanded, and for
every row under it the glyph, the text bands and the in-place editor its Submodule cell opens (the combo items =
the port submodules offered). Then the PN-IO row's Parameter dataset rows. The dialog is closed without keeping,
SYCON.net closed.

Usage:  ..\\.venv\\Scripts\\python -I scripts\\probe_switch.py [--item "SCALANCE XC216-4C V4.4"] [--gsdml <file>]
"""
import argparse
import os
import sys
import time

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP)
from pywinauto import mouse  # noqa: E402

from sycon5 import SyconDriver  # noqa: E402
from sycon5.device import DATASET_COMBO_ID, MODULE_COMBO_ID, MODULE_X, DeviceDialog, row_y  # noqa: E402
from sycon5.session import SyconError, log  # noqa: E402

BASE = os.path.join(APP, "spike", "scratch", "AutomateSyconProj_BaseProj.spj")


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--item", default="SCALANCE XC216-4C V4.4")
    p.add_argument("--gsdml", default="GSDML-V2.45-Siemens-002A-SCALANCE_XC200-20260302.xml")
    a = p.parse_args(argv)
    d = SyconDriver()
    if d.session.attach_if_running():
        raise SystemExit("SYCON.net is running - close it first")
    d.open(BASE)
    d.new_project()
    d.add_controller("CIFX RE/PNM")
    node = d.add_station(a.item, "slave", gsdml=a.gsdml)
    station = node["station"]
    log("switch node:", node, "| output log:", d.session.output_log()[-6:])
    dlg = DeviceDialog(d.session, station)
    try:
        r = dlg.modules_page()
        log("grid:", r, "| slots used:", dlg.slots_used(), "| data length:", dlg.data_length())
        dlg.collapse_all()
        dlg.ensure_expanded(1)
        rows = dlg.visible_rows()
        log("rows with the DAP expanded:", rows, "| glyphs:", [(k, dlg.has_glyph(k)) for k in rows])
        for k in rows[2:8]:
            mouse.click(coords=(r.left + dlg.sx(MODULE_X), r.top + row_y(k)))
            time.sleep(1.0)
            cbs = dlg.controls(("ComboBox",), cid=MODULE_COMBO_ID)
            if cbs:
                log("row %d submodule combo: selected %r, items %r" % (k, cbs[0].selected_text(), cbs[0].item_texts()[:20]))
            else:
                log("row %d: no submodule combo" % k)
            dlg._close_dropdowns()
            dlg.select_row(k)
            cb = dlg.combo(DATASET_COMBO_ID)
            log("   Dataset combo: %r" % ((None if cb is None else (cb.is_enabled(), cb.selected_text())),))
        dlg.select_row(3)
        try:
            pr = dlg.dataset("Parameter")
            log("PN-IO parameter grid:", pr, "| rows y:", dlg.param_rows_y(pr))
        except SyconError as ex:
            log("PN-IO parameters:", ex)
        time.sleep(20)
    finally:
        if dlg.is_open():
            dlg.close(keep=False)
        log("closing SYCON.net:", d.close())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
