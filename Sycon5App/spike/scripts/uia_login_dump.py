"""Spike step 2: press OK on the (empty-credentials) SYCON.net login dialog, then dump the main window tree.

Usage:  python -I uia_login_dump.py [max_depth]
Read-only: it clicks OK on the login dialog and reads the UI Automation tree; nothing is saved.
"""
import sys, time
from pywinauto import Desktop

MAX_DEPTH = int(sys.argv[1]) if len(sys.argv) > 1 else 6
d = Desktop(backend="uia")
login = [w for w in d.windows() if w.window_text() == "SYCON.net User Login"]
if not login:
    for w in d.windows():
        if w.window_text() == "SYCON.net":
            login = [c for c in w.children() if c.window_text() == "SYCON.net User Login"]
            if login:
                break
if login:
    print("login dialog found, pressing OK")
    ok = [c for c in login[0].descendants(control_type="Button") if c.window_text() == "OK"][0]
    ok.click_input()
    time.sleep(8)
else:
    print("no login dialog")

for w in d.windows():
    if "sycon" in w.window_text().lower():
        print("WIN:", repr(w.window_text()), w.class_name(), w.rectangle())


def dump(el, depth=0):
    if depth > MAX_DEPTH:
        return
    try:
        info = el.element_info
        name = (info.name or "")[:70]
        print("  " * depth + f"{info.control_type} | {name!r} | cls={info.class_name} | auto={info.automation_id} | {info.rectangle}")
        for c in el.children():
            dump(c, depth + 1)
    except Exception as e:
        print("  " * depth + f"<err {e}>")


for w in d.windows():
    if "sycon" in w.window_text().lower():
        print("====", w.window_text())
        dump(w)
