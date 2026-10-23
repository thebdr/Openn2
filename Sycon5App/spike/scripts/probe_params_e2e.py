"""Module-parameter probe on the saved round-1 project (read-only: the dialog is Cancelled with its changes
discarded, SYCON.net is closed without saving).

Opens spike/scratch/E2E_Round1.spj, the ET200SP dialog, Modules page; then for each grid row: select it through
a read-only cell, report the Dataset / Display mode combos (ctrl ids 311 / 312), click the Module and Submodule
cells and report the in-place editors; if Dataset enables anywhere, select 'Parameter' and click the lower grid's
cells. Then 'Add Submodule' and the same scan again.

Usage:  python -I scripts/probe_params_e2e.py
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.argv = [sys.argv[0], "--from", "9", "--to", "8"]          # import the e2e helpers without running stages
import importlib.util
spec = importlib.util.spec_from_file_location("e2e", os.path.join(os.path.dirname(os.path.abspath(__file__)), "e2e_round1.py"))
e2e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e2e)
from pywinauto import mouse, Desktop
import win32con
from _probe_lib import (sycon_main, sycon_pids, launch_sycon, login_default, close_sycon_no_save, config_dialogs,
                        dismiss_errors, top_windows)

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJ = os.path.join(HERE, "scratch", "E2E_Round1.spj")
STATION = "n0005-ms1-k2501"
log = e2e.log


def alive(pid):
    return pid in sycon_pids()


# ---- session -------------------------------------------------------------------------------------------------
if not sycon_pids():
    pid = launch_sycon(PROJ)
    main = login_default()
else:
    main = sycon_main()
    pid = main.process_id()
log("main:", main.window_text(), "nodes:", e2e.nodes(main))
dlg = e2e.open_config(main, pid, STATION)
d32 = e2e.w32(dlg)
e2e.select_page(dlg, "Modules")
grid = e2e.pane(dlg, "321")
r = grid.rectangle()
lower = e2e.pane(dlg, "322")
lr = lower.rectangle()
log("modules grid", r, "| lower grid", repr(lower.window_text()), lr)


def texts():
    return [t.window_text()[:100] for t in dlg.descendants(control_type="Text") if t.window_text().startswith(("Use of", "State of"))]


def editors():
    out = []
    for c in d32.descendants():
        try:
            if c.is_visible() and c.class_name() in ("Edit", "ComboBox", "SysIPAddress32", "Button", "ListBox") and c.control_id() >= 1900:
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


def combos():
    out = {}
    for cid in (311, 312):
        c = [c for c in d32.descendants(class_name="ComboBox") if c.control_id() == cid]
        if c:
            out[cid] = (c[0].is_enabled(), c[0].selected_text(), c[0].item_texts())
    return out


def cell_probe(label, x, y):
    before = {(c.class_name(), c.control_id(), str(c.rectangle())) for c in editors()}
    mouse.click(coords=(r.left + x, r.top + y))
    time.sleep(1.0)
    new = [c for c in editors() if (c.class_name(), c.control_id(), str(c.rectangle())) not in before]
    log("   ", label, "-> new editors:", describe(new))
    close_dropdowns()
    return new


def row_scan(rows):
    for row in rows:
        y = 30 + 18 * (row - 1)
        for sx in (10, 30, 450):                               # row header / first column / a read-only cell
            mouse.click(coords=(r.left + sx, r.top + y))
            time.sleep(0.9)
            close_dropdowns()
            log("  row", row, "(y+%d) click x+%d: combos" % (y, sx), combos(), "| editors now:", describe(editors()))
            if combos().get(311, (False,))[0]:
                log("  !! Dataset combo ENABLED on row", row, "after click x+%d" % sx)
                return row
        cell_probe("Slot cell x+60", 60, y)
        cell_probe("Module cell x+150", 150, y)
        cell_probe("Submodule cell x+300", 300, y)
        cell_probe("x+520", 520, y)
        mouse.click(coords=(r.left + 450, r.top + y))
        time.sleep(0.6)
        c = combos()
        if c.get(311, (False,))[0]:
            log("  !! Dataset combo ENABLED on row", row)
            return row
    return None


def lower_scan():
    c311 = [c for c in d32.descendants(class_name="ComboBox") if c.control_id() == 311][0]
    c311.select("Parameter")
    time.sleep(1.5)
    log("  Dataset ->", repr(c311.selected_text()), "| lower grid now", repr(lower.window_text()), lower.rectangle())
    for y in (30, 48, 66, 84):
        for x in (20, 100, 200, 300, 400, 500):
            before = {(c.class_name(), c.control_id(), str(c.rectangle())) for c in editors()}
            mouse.click(coords=(lr.left + x, lr.top + y))
            time.sleep(0.9)
            new = [c for c in editors() if (c.class_name(), c.control_id(), str(c.rectangle())) not in before]
            if new:
                log("    lower grid (x+%d, y+%d):" % (x, y), describe(new))
            close_dropdowns()
            if not alive(pid):
                raise SystemExit("SYCON.net exited")


log("texts:", texts())
log("== row scan (module rows)")
hit = row_scan([1, 2, 3])
if hit:
    lower_scan()
else:
    log("  Dataset combo never enabled on the module rows")
    log("== Add Submodule on row 2 (slot 1, the DI module)")
    mouse.click(coords=(r.left + 450, r.top + 47))
    time.sleep(0.8)
    e2e.press(dlg, pid, "Add Submodule")
    log("  texts after Add Submodule:", texts())
    log("  windows after Add Submodule:", [(w.class_name()[:12], w.window_text()[:40]) for w in Desktop(backend="win32").windows(process=pid, visible_only=True) if w.class_name() not in ("tooltips_class32", "MSCTFIME UI", "IME")])
    log("  visible dialog children (win32, any id):", [(c.class_name(), c.control_id(), c.window_text()[:25]) for c in d32.descendants() if c.is_visible() and c.class_name() in ("Edit", "ComboBox", "ListBox", "SysTreeView32", "SysListView32")][:20])
    hit = row_scan([1, 2, 3, 4, 5])
    if hit:
        lower_scan()
    else:
        log("  Dataset combo never enabled after Add Submodule either")
log("alive:", alive(pid), "| dialogs:", [d.window_text()[:40] for d in config_dialogs(pid)])

# ---- discard and close ----------------------------------------------------------------------------------------
btn = [b for b in d32.descendants(class_name="Button") if b.control_id() == 2 and b.is_visible()][0]
btn.click()
time.sleep(2.0)
for _ in range(10):
    q = [w for w in top_windows(pid) if w.window_text() == "Question"]
    if q:
        w = Desktop(backend="win32").window(handle=q[0].handle)
        txt = [c.window_text()[:80] for c in w.children() if c.class_name() == "Static" and c.window_text()]
        b = [b for b in w.descendants(class_name="Button") if b.control_id() == 7][0]
        log("  Question:", txt, "->", b.window_text())
        b.click()
        time.sleep(2.0)
    if not config_dialogs(pid):
        break
    time.sleep(1.0)
log("dialogs after Cancel:", [d.window_text()[:40] for d in config_dialogs(pid)], "| errors:", dismiss_errors(pid, 10), "| alive:", alive(pid))
log("close:", close_sycon_no_save())
