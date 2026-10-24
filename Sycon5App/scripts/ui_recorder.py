r"""Record the user's UI interactions (user 2026-10-24: "we need to log the ui interactions. a few sycon functions
that change and export data" - the process-data export `HilscherIO.xml` among them), so the driver can replay them.

Polls the mouse and the keyboard (the "pressed since the last check" flag of GetAsyncKeyState catches every press
at a 15 ms poll - no hook library in the venv), identifies the control under every click through UI Automation with
its parent chain (menu > item, dialog > button), logs the keys typed and, when the typing pauses, the focused field
and its value, tracks the top-level windows opening and closing, dumps a dialog's fields when a button in it is
pressed, and saves a PNG of the active window at every click (pure-Python PNG: zlib). Everything goes to
`<folder>/events.log` (one line per event) and `<folder>/NNNN_*.png`.

Usage (from Sycon5App, the repo venv, the desktop the user works on):
    python -I scripts\\ui_recorder.py --out spike\scratch\recordings\<name> [--minutes 30]
Stops after `--minutes`, when the file `<folder>\STOP` appears, or on Ctrl+Alt+Q."""
import argparse
import ctypes
import os
import struct
import sys
import time
import zlib

import win32con
import win32gui
import win32process

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP)
from pywinauto import Desktop                       # noqa: E402
from pywinauto.uia_defines import IUIA              # noqa: E402
from sycon5.drawing import capture                  # noqa: E402

user32 = ctypes.windll.user32
VK_NAMES = {0x08: "Backspace", 0x09: "Tab", 0x0D: "Enter", 0x10: "Shift", 0x11: "Ctrl", 0x12: "Alt", 0x14: "CapsLock",
            0x1B: "Esc", 0x20: "Space", 0x21: "PgUp", 0x22: "PgDn", 0x23: "End", 0x24: "Home", 0x25: "Left",
            0x26: "Up", 0x27: "Right", 0x28: "Down", 0x2D: "Ins", 0x2E: "Del", 0x5B: "Win", 0x5C: "Win",
            0xA0: "Shift", 0xA1: "Shift", 0xA2: "Ctrl", 0xA3: "Ctrl", 0xA4: "Alt", 0xA5: "Alt",
            0x6A: "Num*", 0x6B: "Num+", 0x6D: "Num-", 0x6E: "Num.", 0x6F: "Num/", 0x2C: "PrintScreen", 0x90: "NumLock", 0x91: "ScrollLock",
            0xBA: ";", 0xBB: "=", 0xBC: ",", 0xBD: "-", 0xBE: ".", 0xBF: "/", 0xC0: "`", 0xDB: "[", 0xDC: "\\",
            0xDD: "]", 0xDE: "'"}
for _n in range(1, 25):
    VK_NAMES[0x6F + _n] = "F%d" % _n
MOUSE_VKS = {0x01: "L", 0x02: "R", 0x04: "M"}
MODIFIER_VKS = {0x10, 0x11, 0x12, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5, 0x5B, 0x5C}


class _Rect:
    def __init__(self, left, top, right, bottom):
        self.left, self.top, self.right, self.bottom = left, top, right, bottom

    def width(self):
        return self.right - self.left

    def height(self):
        return self.bottom - self.top


def png_of_window(hwnd, path):
    """The window's client-visible rectangle as a PNG (the screen bits, so menus and dropdowns over it show)."""
    try:
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    except Exception:  # noqa: BLE001
        return False
    sw, sh = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    left, top, right, bottom = max(0, left), max(0, top), min(sw, right), min(sh, bottom)
    if right - left < 8 or bottom - top < 8:
        return False
    bits, stride, bpp, w, h = capture(_Rect(left, top, right, bottom))
    raw = bytearray()
    for y in range(h):
        row = bits[y * stride:(y + 1) * stride]
        raw.append(0)                                       # filter none
        line = bytearray(w * 3)
        for x in range(w):
            b, g, r = row[x * bpp], row[x * bpp + 1], row[x * bpp + 2]
            line[x * 3], line[x * 3 + 1], line[x * 3 + 2] = r, g, b
        raw += line

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 6)) + chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)
    return True


def key_name(vk):
    if vk in VK_NAMES:
        return VK_NAMES[vk]
    if 0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A:
        return chr(vk)
    if 0x60 <= vk <= 0x69:
        return "Num%d" % (vk - 0x60)
    return "VK%02X" % vk


def modifiers():
    mods = []
    for vk, name in ((0x11, "Ctrl"), (0x12, "Alt"), (0x10, "Shift"), (0x5B, "Win")):
        if user32.GetAsyncKeyState(vk) & 0x8000:
            mods.append(name)
    return mods


def describe(wrapper, depth=6):
    """`Type "name" [auto_id] (class)` of an element and its parents up to the top window, innermost first."""
    chain = []
    el = wrapper
    for _ in range(depth):
        if el is None:
            break
        try:
            info = el.element_info
            text = '%s "%s"' % (info.control_type, (info.name or "")[:60])
            if info.automation_id:
                text += " [%s]" % info.automation_id
            if info.class_name and info.control_type not in ("MenuItem", "Button"):
                text += " (%s)" % info.class_name
            chain.append(text)
            el = el.parent()
        except Exception:  # noqa: BLE001
            break
    return " < ".join(chain)


def dialog_fields(wrapper):
    """The visible Edit / ComboBox / CheckBox values of the clicked element's top-level window (a dialog)."""
    try:
        top = wrapper.top_level_parent()
    except Exception:  # noqa: BLE001
        return ""
    out = []
    try:
        for c in top.descendants():
            info = c.element_info
            if info.control_type in ("Edit", "ComboBox", "CheckBox", "RadioButton") and c.is_visible():
                try:
                    value = c.get_value() if hasattr(c, "get_value") else ""
                except Exception:  # noqa: BLE001
                    value = ""
                if not value:
                    try:
                        value = c.window_text()
                    except Exception:  # noqa: BLE001
                        value = ""
                if info.control_type in ("CheckBox", "RadioButton"):
                    try:
                        value = str(c.get_toggle_state()) if hasattr(c, "get_toggle_state") else value
                    except Exception:  # noqa: BLE001
                        pass
                label = info.name or info.automation_id or info.class_name
                out.append('%s "%s"=%r' % (info.control_type, (label or "")[:40], str(value)[:120]))
    except Exception:  # noqa: BLE001
        pass
    return " | ".join(out[:40])


def focused():
    try:
        el = IUIA().iuia.GetFocusedElement()
        from pywinauto.uia_element_info import UIAElementInfo
        from pywinauto.controls.uiawrapper import UIAWrapper
        w = UIAWrapper(UIAElementInfo(el))
        value = ""
        try:
            value = w.get_value() if hasattr(w, "get_value") else ""
        except Exception:  # noqa: BLE001
            pass
        if not value:
            try:
                value = w.window_text()
            except Exception:  # noqa: BLE001
                value = ""
        return describe(w, depth=3), str(value)[:200]
    except Exception as ex:  # noqa: BLE001
        return "(%s)" % type(ex).__name__, ""


def top_windows():
    found = {}

    def cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if title:
                _tid, pid = win32process.GetWindowThreadProcessId(hwnd)
                found[hwnd] = (title, win32gui.GetClassName(hwnd), pid)
        return True
    win32gui.EnumWindows(cb, None)
    return found


def main(argv=None):
    ap = argparse.ArgumentParser(description="record the UI interactions of the desktop")
    ap.add_argument("--out", required=True)
    ap.add_argument("--minutes", type=float, default=30.0)
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    stop_file = os.path.join(a.out, "STOP")
    if os.path.exists(stop_file):
        os.remove(stop_file)
    log_path = os.path.join(a.out, "events.log")
    logf = open(log_path, "a", encoding="utf-8")

    def log(text):
        line = time.strftime("%H:%M:%S") + ".%03d " % (int(time.time() * 1000) % 1000) + text
        logf.write(line + "\n")
        logf.flush()

    desktop = Desktop(backend="uia")
    for vk in list(MOUSE_VKS) + list(range(0x08, 0xFF)):
        user32.GetAsyncKeyState(vk)                       # clear the "pressed since" flags
    windows = top_windows()
    log("recorder started; %d visible windows; the SYCON.net ones: %s" % (
        len(windows), [t for t, c, p in windows.values() if "SYCON" in t.upper() or "netDevice" in t]))
    shot, keys, last_key_time = 0, [], 0.0
    t0, last_windows_check = time.time(), 0.0
    while True:
        now = time.time()
        if now - t0 > a.minutes * 60 or os.path.exists(stop_file):
            log("recorder stopped (%s)" % ("STOP file" if os.path.exists(stop_file) else "time is up"))
            break
        # --- clicks
        for vk, button in MOUSE_VKS.items():
            state = user32.GetAsyncKeyState(vk)
            if state & 1:                                   # pressed since the last check
                x, y = win32gui.GetCursorPos()
                time.sleep(0.05)
                fg = win32gui.GetForegroundWindow()
                title = win32gui.GetWindowText(fg)
                try:
                    el = desktop.from_point(x, y)
                    what = describe(el)
                    ctype = el.element_info.control_type
                except Exception as ex:  # noqa: BLE001
                    el, what, ctype = None, "(%s)" % type(ex).__name__, ""
                mods = "+".join(modifiers())
                line = 'click %s%s (%d,%d) win="%s" at %s' % (button, "+" + mods if mods else "", x, y, title[:80], what)
                if el is not None and ctype in ("Button", "SplitButton", "MenuItem", "TabItem", "ListItem", "TreeItem"):
                    fields = dialog_fields(el) if ctype in ("Button", "SplitButton") else ""
                    if fields:
                        line += " | fields: " + fields
                log(line)
                time.sleep(0.35)                             # menus and dialogs render
                shot += 1
                fg2 = win32gui.GetForegroundWindow()
                png = os.path.join(a.out, "%04d_click.png" % shot)
                if png_of_window(fg2, png):
                    log("  screenshot %s of \"%s\"" % (os.path.basename(png), win32gui.GetWindowText(fg2)[:80]))
        # --- keys
        for vk in range(0x08, 0xFF):
            if vk in MOUSE_VKS:
                continue
            if user32.GetAsyncKeyState(vk) & 1:
                if vk in MODIFIER_VKS:
                    continue
                mods = [m for m in modifiers() if m != "Shift" or not (0x30 <= vk <= 0x5A)]
                name = key_name(vk)
                if "Ctrl" in mods and "Alt" in mods and vk == 0x51:
                    log("recorder stopped (Ctrl+Alt+Q)")
                    logf.close()
                    return 0
                if 0x41 <= vk <= 0x5A and not (user32.GetKeyState(0x14) & 1) == bool(user32.GetAsyncKeyState(0x10) & 0x8000):
                    name = name.lower()
                keys.append("+".join(mods + [name]) if mods else name)
                last_key_time = now
        if keys and now - last_key_time > 0.7:
            where, value = focused()
            log("keys: %s | focus: %s value=%r" % (" ".join(keys), where, value))
            keys = []
        # --- windows
        if now - last_windows_check > 0.3:
            last_windows_check = now
            current = top_windows()
            for hwnd, (title, cls, pid) in current.items():
                if hwnd not in windows:
                    log('window opened: "%s" (%s, pid %d)' % (title[:100], cls, pid))
            for hwnd, (title, cls, pid) in windows.items():
                if hwnd not in current:
                    log('window closed: "%s" (%s)' % (title[:100], cls))
            windows = current
        time.sleep(0.015)
    logf.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
