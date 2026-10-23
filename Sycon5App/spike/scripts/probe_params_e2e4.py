"""Module-parameter probe, fourth form (read-only: dialogs Cancelled with changes discarded, SYCON.net closed
without saving). Known now: double-click the DAP row's glyph (x+17) -> its submodule rows; select the first one
(x+560) -> the Dataset combo (311) enables; 'Parameter' -> the lower pane becomes CParamGrid (auto id 320).
This probe drills into that grid: pixel bands with a looser threshold, double-clicks on its row glyphs (records
may be collapsed), clicks on every column of every row -> the in-place editors (win32, ids >= 1900).
Done for the ET200SP and the NORD. Cancel = win32 BM_CLICK, then UIA click as the fallback, Question -> No.

Usage:  python -I scripts/probe_params_e2e4.py
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
                        dismiss_errors, top_windows, safe_click)

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


def answer_question_no():
    for w in top_windows(pid):
        if w.window_text() == "Question":
            ww = Desktop(backend="win32").window(handle=w.handle)
            b = [b for b in ww.descendants(class_name="Button") if b.control_id() == 7][0]
            b.click()
            time.sleep(2.0)
            return True
    return False


def text_bands(rect, thr=600, x0=40):
    bits, stride, bpp, w, h = capture(rect)
    out = []
    for y0 in range(0, h - BAND + 1, BAND):
        n = 0
        for y in range(y0, y0 + BAND):
            row = bits[y * stride:(y + 1) * stride]
            n += sum(1 for x in range(x0, w) if (row[x * bpp] + row[x * bpp + 1] + row[x * bpp + 2]) < thr)
        out.append((y0, n))
    return out


def close_dialog(dlg, d32):
    dismiss_errors(pid, 10)
    btn = [b for b in d32.descendants(class_name="Button") if b.control_id() == 2 and b.is_visible()][0]
    btn.click()
    time.sleep(2.0)
    for i in range(12):
        answer_question_no()
        if not config_dialogs(pid):
            return True
        if i == 5:
            log("  Cancel by message ignored -> UIA click on Cancel")
            try:
                b = [b for b in dlg.descendants(control_type="Button") if b.window_text().replace("&", "") == "Cancel"][0]
                safe_click(b, pid, allow_menu=True)
            except Exception as ex:  # noqa: BLE001
                log("  UIA Cancel failed:", ex)
        time.sleep(1.0)
    return not config_dialogs(pid)


def probe_station(station):
    dlg = e2e.open_config(main, pid, station)
    d32 = e2e.w32(dlg)
    e2e.select_page(dlg, "Modules")
    r = e2e.pane(dlg, "321").rectangle()

    def editors():
        out = []
        for c in d32.descendants():
            try:
                if c.is_visible() and c.class_name() in ("Edit", "ComboBox", "SysIPAddress32", "ListBox", "Button") and c.control_id() >= 1900:
                    out.append(c)
            except Exception:  # noqa: BLE001
                pass
        return out

    def describe(cs):
        out = []
        for c in cs:
            try:
                if c.class_name() == "ComboBox":
                    out.append(("ComboBox", c.control_id(), c.selected_text(), c.item_texts()[:10]))
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

    rows = [y0 for y0, n in text_bands(r, 450) if n > 30]
    log(station, "| modules grid", r, "| text rows y0:", rows)
    if len(rows) <= 3:                                           # header + DAP + modules: expand the DAP row
        mouse.double_click(coords=(r.left + 17, r.top + 18 + BAND // 2))
        time.sleep(1.2)
        close_dropdowns()
        rows = [y0 for y0, n in text_bands(r, 450) if n > 30]
        log("  after expanding the DAP row: text rows y0:", rows)
    mouse.click(coords=(r.left + 560, r.top + 54 + BAND // 2))   # the DAP's first submodule row
    time.sleep(0.8)
    close_dropdowns()
    en, sel = c311()
    log("  DAP submodule row selected: Dataset enabled=%s (%r)" % (en, sel))
    if not en:
        log("  -> not enabled; giving up on", station)
        close_dialog(dlg, d32)
        return
    c = [c for c in d32.descendants(class_name="ComboBox") if c.control_id() == 311][0]
    c.select("Parameter")
    time.sleep(2.0)
    lows = [p for p in dlg.descendants(control_type="Pane") if p.rectangle().top > r.bottom and p.class_name().startswith("C")]
    log("  Dataset ->", repr(c.selected_text()), "| lower panes:", [(p.element_info.automation_id, p.class_name(), p.window_text()[:20], str(p.rectangle())) for p in lows])
    pg = [p for p in lows if p.class_name() == "CParamGrid"]
    if not pg:
        log("  no CParamGrid")
        close_dialog(dlg, d32)
        return
    lr = pg[0].rectangle()
    log("  param grid", lr, "| bands thr 600 (y0, dark px):", [(y0, n) for y0, n in text_bands(lr, 600, 0) if n > 0])
    log("  param grid UIA children:", [(e.element_info.control_type, e.window_text()[:30]) for e in pg[0].descendants()][:10])
    # expand whatever rows the grid shows (records may be collapsed), then click every cell
    for y0 in [y0 for y0, n in text_bands(lr, 600, 0) if n > 0][1:4]:
        before_rows = [y for y, n in text_bands(lr, 600, 0) if n > 0]
        mouse.double_click(coords=(lr.left + 17, lr.top + y0 + BAND // 2))
        time.sleep(1.0)
        close_dropdowns()
        after_rows = [y for y, n in text_bands(lr, 600, 0) if n > 0]
        log("  double-click glyph of param row y0=%d: rows %s -> %s" % (y0, before_rows, after_rows))
    rows = [y for y, n in text_bands(lr, 600, 0) if n > 0]
    for y0 in rows[1:7]:
        for x in (20, 60, 140, 240, 340, 440, 520):
            before = {(c.class_name(), c.control_id(), str(c.rectangle())) for c in editors()}
            mouse.click(coords=(lr.left + x, lr.top + y0 + BAND // 2))
            time.sleep(0.8)
            new = [c for c in editors() if (c.class_name(), c.control_id(), str(c.rectangle())) not in before]
            if new:
                log("    param grid row y0=%d x+%d:" % (y0, x), describe(new))
            close_dropdowns()
            if [w for w in top_windows(pid) if w.window_text() == "Error"]:
                log("    !! Error:", dismiss_errors(pid, 5))
            if not sycon_pids():
                raise SystemExit("SYCON.net exited")
    log("  closed:", close_dialog(dlg, d32), "| alive:", bool(sycon_pids()))


dismiss_errors(pid, 10)
answer_question_no()
for st in ("n0005-ms1-k2501", "sk-cu4-eth"):
    if config_dialogs(pid):                                      # a dialog left open by an earlier probe
        d = config_dialogs(pid)[0]
        log("closing leftover dialog:", d.window_text()[:50], "->", close_dialog(d, e2e.w32(d)))
    probe_station(st)
log("close:", close_sycon_no_save())
