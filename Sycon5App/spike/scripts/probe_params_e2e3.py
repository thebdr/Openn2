"""Module-parameter probe, third form (read-only: dialogs Cancelled with changes discarded, SYCON.net closed
without saving). A module row expands on a DOUBLE-CLICK of its glyph (x+17); the submodule rows appear below.
The saved project shows a parameter record under the DAP's submodule (STLRecordParamDataMap), so the DAP row is
expanded first, then every new row is selected and the Dataset combo (311) checked; when it enables, 'Parameter'
is selected and the lower grid's cells are clicked to find the editors. Done for the ET200SP and the NORD.

Usage:  python -I scripts/probe_params_e2e3.py
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.argv = [sys.argv[0], "--from", "9", "--to", "8"]
import importlib.util
spec = importlib.util.spec_from_file_location("e2e", os.path.join(os.path.dirname(os.path.abspath(__file__)), "e2e_round1.py"))
e2e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e2e)
from pywinauto import mouse, Desktop
import win32con
from find_buslines import capture
from _probe_lib import (sycon_main, sycon_pids, launch_sycon, login_default, close_sycon_no_save, config_dialogs,
                        dismiss_errors, top_windows)

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJ = os.path.join(HERE, "scratch", "E2E_Round1.spj")
log = e2e.log
BAND = 18

if not sycon_pids():
    pid = launch_sycon(PROJ)
    main = login_default()
else:
    main = sycon_main()
    pid = main.process_id()


def text_bands(rect):
    bits, stride, bpp, w, h = capture(rect)
    out = []
    for y0 in range(0, h - BAND + 1, BAND):
        n = 0
        for y in range(y0, y0 + BAND):
            row = bits[y * stride:(y + 1) * stride]
            n += sum(1 for x in range(40, w) if (row[x * bpp] + row[x * bpp + 1] + row[x * bpp + 2]) < 450)
        out.append((y0, n))
    return [y0 for y0, n in out if n > 30]


def probe_station(station):
    dlg = e2e.open_config(main, pid, station)
    d32 = e2e.w32(dlg)
    e2e.select_page(dlg, "Modules")
    r = e2e.pane(dlg, "321").rectangle()

    def editors():
        out = []
        for c in d32.descendants():
            try:
                if c.is_visible() and c.class_name() in ("Edit", "ComboBox", "SysIPAddress32", "ListBox") and c.control_id() >= 1900:
                    out.append(c)
            except Exception:  # noqa: BLE001
                pass
        return out

    def describe(cs):
        out = []
        for c in cs:
            try:
                if c.class_name() == "ComboBox":
                    out.append(("ComboBox", c.control_id(), c.selected_text(), c.item_texts()[:8]))
                else:
                    out.append((c.class_name(), c.control_id(), c.window_text()[:40]))
            except Exception as ex:  # noqa: BLE001
                out.append((c.class_name(), c.control_id(), "read failed %r" % ex))
        return out

    def close_dropdowns():
        for c in editors():
            if c.class_name() == "ComboBox":
                c.send_message(win32con.CB_SHOWDROPDOWN, 0, 0)

    def c311():
        c = [c for c in d32.descendants(class_name="ComboBox") if c.control_id() == 311][0]
        return c.is_enabled(), c.selected_text()

    def select_row(y0):
        mouse.click(coords=(r.left + 560, r.top + y0 + BAND // 2))
        time.sleep(0.8)
        close_dropdowns()

    rows0 = text_bands(r)
    log(station, "| grid", r, "| text rows at y0:", rows0)
    found = None
    for y0 in list(rows0[1:]):                                   # skip the header band
        rows_before = text_bands(r)
        mouse.double_click(coords=(r.left + 17, r.top + y0 + BAND // 2))
        time.sleep(1.2)
        close_dropdowns()
        rows_after = text_bands(r)
        new_rows = [b for b in rows_after if b not in rows_before]
        log("  double-click glyph of row y0=%d -> rows now %s, new %s" % (y0, rows_after, new_rows))
        for ny in new_rows:
            select_row(ny)
            en, sel = c311()
            log("    new row y0=%d selected: Dataset enabled=%s (%r) | editors %s" % (ny, en, sel, describe(editors())))
            if en:
                found = ny
                break
        if found is not None:
            break
        for ny in new_rows:                                      # collapse again before the next row
            pass
    if found is None:
        log("  Dataset combo never enabled for", station)
    else:
        c = [c for c in d32.descendants(class_name="ComboBox") if c.control_id() == 311][0]
        c.select("Parameter")
        time.sleep(2.0)
        log("  Dataset ->", repr(c.selected_text()))
        lows = [p for p in dlg.descendants(control_type="Pane") if p.rectangle().top > r.bottom and p.class_name().startswith("C")]
        log("  lower panes:", [(p.element_info.automation_id, p.class_name(), p.window_text()[:20], str(p.rectangle())) for p in lows])
        lr = lows[0].rectangle() if lows else e2e.pane(dlg, "322").rectangle()
        log("  lower grid text rows at y0:", text_bands(lr))
        for yy in range(27, min(lr.height(), 27 + BAND * 6), BAND):
            for x in (20, 120, 220, 320, 420, 520):
                before = {(c.class_name(), c.control_id(), str(c.rectangle())) for c in editors()}
                mouse.click(coords=(lr.left + x, lr.top + yy))
                time.sleep(0.9)
                new = [c for c in editors() if (c.class_name(), c.control_id(), str(c.rectangle())) not in before]
                if new:
                    log("    lower grid (x+%d, y+%d):" % (x, yy), describe(new))
                close_dropdowns()
                if [w for w in top_windows(pid) if w.window_text() == "Error"]:
                    log("    !! Error:", dismiss_errors(pid, 5))
                if not sycon_pids():
                    raise SystemExit("SYCON.net exited")
    dismiss_errors(pid, 10)
    btn = [b for b in d32.descendants(class_name="Button") if b.control_id() == 2 and b.is_visible()][0]
    btn.click()
    time.sleep(2.0)
    for _ in range(10):
        q = [w for w in top_windows(pid) if w.window_text() == "Question"]
        if q:
            w = Desktop(backend="win32").window(handle=q[0].handle)
            b = [b for b in w.descendants(class_name="Button") if b.control_id() == 7][0]
            b.click()
            time.sleep(2.0)
        if not config_dialogs(pid):
            break
        time.sleep(1.0)
    log("  dialog closed:", not config_dialogs(pid), "| alive:", bool(sycon_pids()))


for st in ("n0005-ms1-k2501", "sk-cu4-eth"):
    probe_station(st)
log("close:", close_sycon_no_save())
