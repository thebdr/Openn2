"""Module-parameter probe, second form (read-only: dialog Cancelled with changes discarded, SYCON.net closed
without saving). The help says the modules table hides the submodule rows behind a '+' (click it or press the
spacebar on the selected row) and that the Dataset area shows the selected submodule's I/O data or Parameters.

Opens spike/scratch/E2E_Round1.spj, the ET200SP dialog, Modules page; selects row 2 (slot 1, DI 8x24VDC HF),
expands it (click on its '+', then spacebar as the fallback), selects the rows below it and reports the Dataset
combo; when it enables, switches to 'Parameter' and clicks the lower grid's cells to find the editors.

Usage:  python -I scripts/probe_params_e2e2.py
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.argv = [sys.argv[0], "--from", "9", "--to", "8"]
import importlib.util
spec = importlib.util.spec_from_file_location("e2e", os.path.join(os.path.dirname(os.path.abspath(__file__)), "e2e_round1.py"))
e2e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e2e)
from pywinauto import mouse, keyboard, Desktop
import win32con
from _probe_lib import (sycon_main, sycon_pids, launch_sycon, login_default, close_sycon_no_save, config_dialogs,
                        dismiss_errors, top_windows)

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJ = os.path.join(HERE, "scratch", "E2E_Round1.spj")
STATION = "n0005-ms1-k2501"
log = e2e.log

if not sycon_pids():
    pid = launch_sycon(PROJ)
    main = login_default()
else:
    main = sycon_main()
    pid = main.process_id()
dlg = e2e.open_config(main, pid, STATION)
d32 = e2e.w32(dlg)
e2e.select_page(dlg, "Modules")
r = e2e.pane(dlg, "321").rectangle()
log("modules grid", r)


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
                out.append(("ComboBox", c.control_id(), c.selected_text(), c.item_count()))
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


def errors_now():
    return [w.window_text() for w in top_windows(pid) if w.window_text() == "Error"]


def lower_panes():
    return [(p.element_info.automation_id, p.class_name(), p.window_text()[:20], str(p.rectangle()))
            for p in dlg.descendants(control_type="Pane") if p.rectangle().top > r.bottom and p.class_name().startswith("C")]


def row_y(n):
    return 30 + 18 * (n - 1)


def report(label):
    log(" ", label, "| Dataset:", c311(), "| editors:", describe(editors()), "| errors:", errors_now())


# 1. select row 2 through a read-only cell, then try to expand it
mouse.click(coords=(r.left + 450, r.top + row_y(2)))
time.sleep(0.8)
report("row 2 selected (x+450)")
for x in (6, 12, 18, 24):
    mouse.click(coords=(r.left + x, r.top + row_y(2)))
    time.sleep(0.9)
    close_dropdowns()
    report("click (x+%d, row 2) = '+' candidate" % x)
    mouse.click(coords=(r.left + 450, r.top + row_y(3)))
    time.sleep(0.9)
    close_dropdowns()
    report("  then row 3 selected (x+450)")
    if c311()[0]:
        break
if not c311()[0]:
    mouse.click(coords=(r.left + 450, r.top + row_y(2)))
    time.sleep(0.6)
    keyboard.send_keys(" ")                               # spacebar expands the selected row (help)
    time.sleep(1.0)
    report("spacebar on row 2")
    for n in (3, 4):
        mouse.click(coords=(r.left + 450, r.top + row_y(n)))
        time.sleep(0.9)
        close_dropdowns()
        report("row %d selected" % n)
        if c311()[0]:
            break
# 2. the submodule row: its cells
if c311()[0]:
    y = None
    for n in (3, 4):
        mouse.click(coords=(r.left + 450, r.top + row_y(n)))
        time.sleep(0.8)
        if c311()[0]:
            y = row_y(n)
            break
    log("submodule row at y+%s" % y)
    for x in (60, 150, 300):
        before = {(c.class_name(), c.control_id(), str(c.rectangle())) for c in editors()}
        mouse.click(coords=(r.left + x, r.top + y))
        time.sleep(1.0)
        new = [c for c in editors() if (c.class_name(), c.control_id(), str(c.rectangle())) not in before]
        log("  submodule row cell x+%d -> new editors:" % x, describe(new))
        close_dropdowns()
    mouse.click(coords=(r.left + 450, r.top + y))
    time.sleep(0.6)
    # 3. Dataset -> Parameter, then the lower grid
    c = [c for c in d32.descendants(class_name="ComboBox") if c.control_id() == 311][0]
    log("lower panes before:", lower_panes())
    c.select("Parameter")
    time.sleep(2.0)
    log("Dataset ->", repr(c.selected_text()), "| lower panes after:", lower_panes())
    lows = [p for p in dlg.descendants(control_type="Pane") if p.rectangle().top > r.bottom and p.class_name().startswith("C")]
    lr = lows[0].rectangle() if lows else e2e.pane(dlg, "322").rectangle()
    for yy in (30, 48, 66, 84, 102):
        for x in (20, 100, 200, 300, 400, 500):
            before = {(c.class_name(), c.control_id(), str(c.rectangle())) for c in editors()}
            mouse.click(coords=(lr.left + x, lr.top + yy))
            time.sleep(0.9)
            new = [c for c in editors() if (c.class_name(), c.control_id(), str(c.rectangle())) not in before]
            if new:
                log("  lower grid (x+%d, y+%d):" % (x, yy), describe(new))
                for cc in new:
                    if cc.class_name() == "ComboBox":
                        try:
                            log("     items:", cc.item_texts()[:12])
                        except Exception:  # noqa: BLE001
                            pass
            close_dropdowns()
            if errors_now():
                log("  !! Error box:", errors_now())
                dismiss_errors(pid, 5)
            if not sycon_pids():
                raise SystemExit("SYCON.net exited")
else:
    log("Dataset combo still disabled - submodule row not reachable this way")

# discard and close
dismiss_errors(pid, 10)
btn = [b for b in d32.descendants(class_name="Button") if b.control_id() == 2 and b.is_visible()][0]
btn.click()
time.sleep(2.0)
for _ in range(10):
    q = [w for w in top_windows(pid) if w.window_text() == "Question"]
    if q:
        w = Desktop(backend="win32").window(handle=q[0].handle)
        b = [b for b in w.descendants(class_name="Button") if b.control_id() == 7][0]
        log("  Question ->", b.window_text())
        b.click()
        time.sleep(2.0)
    if not config_dialogs(pid):
        break
    time.sleep(1.0)
log("dialogs after Cancel:", [d.window_text()[:40] for d in config_dialogs(pid)], "| alive:", bool(sycon_pids()))
log("close:", close_sycon_no_save())
