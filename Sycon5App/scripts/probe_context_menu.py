"""List the controller node's context menu and its 'Additional Functions' submenu (the recorder of 2026-10-24
19:11 saw the user's clicks there but a menu closes before the item under the cursor can be read). Opens the
project, reads the menus, presses Escape, closes SYCON.net - nothing saved. Saves a screenshot per step into
spike/scratch/recordings/_probe_menu/.
Usage (from Sycon5App, the repo venv):  python -I scripts\\probe_context_menu.py --project <spj>"""
import argparse
import os
import sys
import time

import win32gui

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP)
sys.path.insert(0, os.path.join(APP, "scripts"))

from pywinauto import Desktop, keyboard, mouse        # noqa: E402
from sycon5 import SyconDriver                       # noqa: E402
from sycon5.session import log                       # noqa: E402
from ui_recorder import png_of_window                # noqa: E402

OUT = os.path.join(APP, "spike", "scratch", "recordings", "_probe_menu")
os.makedirs(OUT, exist_ok=True)


def popups():
    """[(hwnd, rect)] of the visible Win32 popup-menu windows (class #32768)."""
    found = []

    def cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd) and win32gui.GetClassName(hwnd) == "#32768":
            found.append((hwnd, win32gui.GetWindowRect(hwnd)))
        return True
    win32gui.EnumWindows(cb, None)
    return found


def items_of(hwnd):
    desk = Desktop(backend="uia")
    try:
        w = desk.window(handle=hwnd)
        return [mi.window_text() for mi in w.descendants(control_type="MenuItem")]
    except Exception as ex:  # noqa: BLE001
        return ["(%s)" % type(ex).__name__]


def snap(name):
    path = os.path.join(OUT, name + ".png")
    png_of_window(win32gui.GetDesktopWindow(), path)
    log("  popups:", [(h, r, items_of(h)) for h, r in popups()], "->", name)


p = argparse.ArgumentParser()
p.add_argument("--project", required=True)
a = p.parse_args()
d = SyconDriver()
try:
    d.open(a.project)
    s = d.session
    s.close_menus()
    s.bring_front()
    item = s.station_item(d.controller_station())
    item.ensure_visible()
    item.click_input(button="right")
    time.sleep(1.2)
    snap("01_context_menu")
    desk = Desktop(backend="uia")
    menus = [w for w in desk.windows() if w.class_name() == "#32768"]
    target = [mi for mi in menus[0].descendants(control_type="MenuItem") if mi.window_text().startswith("Additional")] if menus else []
    if target:
        mi = target[0]
        r = mi.rectangle()
        log("Additional Functions at", (r.left, r.top, r.right, r.bottom))
        # 1. the element's own click
        try:
            mi.click_input()
        except Exception as ex:  # noqa: BLE001
            log("  click_input:", ex)
        time.sleep(1.5)
        snap("02_after_click_input")
        # the nested levels: every entry without '...' of the submenu is opened the same way and listed
        for h, _r in popups():
            if h == menus[0].handle:
                continue
            sub = desk.window(handle=h)
            for entry in [mi2 for mi2 in sub.descendants(control_type="MenuItem") if not mi2.window_text().endswith("...")]:
                try:
                    entry.click_input()
                except Exception as ex:  # noqa: BLE001
                    log("  click on %r: %s" % (entry.window_text(), ex))
                    continue
                time.sleep(1.5)
                snap("02_%s" % entry.window_text().replace(" ", "_"))
        if len(popups()) < 2:
            # 2. a hover held longer
            mouse.move(coords=((r.left + r.right) // 2, (r.top + r.bottom) // 2))
            time.sleep(2.5)
            snap("03_after_long_hover")
        if len(popups()) < 2:
            # 3. the keyboard: the item is highlighted under the cursor, Right opens its submenu
            keyboard.send_keys("{RIGHT}")
            time.sleep(1.5)
            snap("04_after_right_key")
        if len(popups()) < 2:
            try:
                mi.expand()
            except Exception as ex:  # noqa: BLE001
                log("  expand:", ex)
            time.sleep(1.5)
            snap("05_after_expand")
    keyboard.send_keys("{ESC}{ESC}{ESC}")
    time.sleep(0.5)
finally:
    log("close:", d.close())
