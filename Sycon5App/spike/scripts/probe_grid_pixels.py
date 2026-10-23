"""Pixel analysis of the Modules grid (custom-drawn): which row bands hold text, where the column separators
and the expander box are, and whether keypad '+' / Right / spacebar on the module row adds a row band
(= the submodule row). Read-only: the dialog is Cancelled with changes discarded, SYCON.net closed.

Usage:  python -I scripts/probe_grid_pixels.py
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
from find_buslines import capture
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
grid = e2e.pane(dlg, "321")
r = grid.rectangle()
log("modules grid", r)


def dark_map():
    bits, stride, bpp, w, h = capture(r)
    rows = []
    for y in range(h):
        row = bits[y * stride:(y + 1) * stride]
        rows.append([(row[x * bpp] + row[x * bpp + 1] + row[x * bpp + 2]) < 450 for x in range(w)])
    return rows, w, h


def bands(rows, w, h, band=18, top=0):
    out = []
    for y0 in range(top, h - band + 1, band):
        n = sum(sum(rows[y][0:w]) for y in range(y0, y0 + band))
        first = None
        for y in range(y0, y0 + band):
            if any(rows[y][40:w]):
                first = True
                break
        out.append((y0, n, bool(first)))
    return out


def columns(rows, w, h):
    """x positions where a vertical dark line spans most of the grid height = column separators."""
    seps = []
    for x in range(w):
        n = sum(rows[y][x] for y in range(h))
        if n > h * 0.6:
            seps.append(x)
    return seps


def expander(rows, y0, band=18):
    """dark pixels in the first 40 px of a row band, as a column histogram."""
    return [sum(rows[y][x] for y in range(y0, y0 + band)) for x in range(0, 40)]


def c311():
    c = [c for c in d32.descendants(class_name="ComboBox") if c.control_id() == 311][0]
    return c.is_enabled(), c.selected_text()


def close_dropdowns():
    for c in d32.descendants(class_name="ComboBox"):
        if c.is_visible() and c.control_id() >= 1900:
            c.send_message(win32con.CB_SHOWDROPDOWN, 0, 0)


def snapshot(label):
    rows, w, h = dark_map()
    b = bands(rows, w, h)
    log(label, "| grid", w, "x", h, "| bands (y0, dark px, text beyond x=40):", [(y0, n, t) for y0, n, t in b if n > 0][:10])
    log("   column separators x:", columns(rows, w, h)[:20])
    for y0, n, t in b[1:4]:
        log("   band y0=%d left-40px histogram:" % y0, expander(rows, y0))
    return b


b0 = snapshot("initial")
mouse.click(coords=(r.left + 560, r.top + 48))          # select row 2 at the far right (Full Access column?)
time.sleep(0.8)
close_dropdowns()
log("after click (x+560, row 2): Dataset", c311(), "| editors:", [(c.class_name(), c.control_id()) for c in d32.descendants() if c.is_visible() and c.control_id() >= 1900 and c.class_name() in ("Edit", "ComboBox")])
snapshot("after selecting row 2")
for keys, label in (("{VK_ADD}", "keypad +"), ("{+}", "plus"), ("{RIGHT}", "Right"), (" ", "spacebar"), (None, "double-click glyph x+17"), (None, "double-click row x+300")):
    mouse.click(coords=(r.left + 560, r.top + 48))
    time.sleep(0.6)
    close_dropdowns()
    if keys:
        keyboard.send_keys(keys)
    elif "glyph" in label:
        mouse.double_click(coords=(r.left + 17, r.top + 45))
    else:
        mouse.double_click(coords=(r.left + 300, r.top + 45))
    time.sleep(1.0)
    close_dropdowns()
    b = snapshot("after " + label + " on row 2")
    log("   Dataset:", c311())
    if sum(1 for _, n, t in b if t) > sum(1 for _, n, t in b0 if t):
        log("   !! a new row band appeared after", label)
        for n_ in (3, 4):
            mouse.click(coords=(r.left + 560, r.top + 30 + 18 * (n_ - 1)))
            time.sleep(0.8)
            close_dropdowns()
            log("   row", n_, "selected: Dataset", c311())
        break

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
log("dialogs after Cancel:", [d.window_text()[:40] for d in config_dialogs(pid)], "| alive:", bool(sycon_pids()))
log("close:", close_sycon_no_save())
