"""Dump the main menus by keyboard (Alt+letter), read-only: each popup is dumped then closed with Esc.

Usage:  python -I scripts/probe_menus_kbd.py [letters]   (default fvdneh = File View Device Network Extras Help)
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pywinauto import keyboard
from _probe_lib import sycon_main, bring_front, dump, wait_menu, close_menus, dismiss_errors

LETTERS = sys.argv[1] if len(sys.argv) > 1 else "fvdneh"
main = sycon_main(); pid = main.process_id()
dismiss_errors(pid, 50); close_menus(); bring_front(main)
with open("uia_menus_kbd.txt", "w", encoding="utf-8") as f:
    for ch in LETTERS:
        keyboard.send_keys("%" + ch)
        m = wait_menu(6)
        print(f"==== Alt+{ch}: popup={bool(m)}", file=f)
        if m:
            for it in m.children():
                print(f"  {it.element_info.control_type} | {it.window_text()!r} | auto={it.element_info.automation_id}", file=f)
        keyboard.send_keys("{ESC}"); time.sleep(0.4); close_menus(); time.sleep(0.3)
print(open("uia_menus_kbd.txt", encoding="utf-8").read())
