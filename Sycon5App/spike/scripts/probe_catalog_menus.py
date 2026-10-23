"""Step 4/5 (read-only): dump the device catalog trees (PROFINET IO expanded through the UIA ExpandCollapse
pattern, no clicks) and the main menus (File, View, Device, Network, Extras, Help - each opened and Esc'd).

Usage:  python -I scripts/probe_catalog_menus.py [out.txt]
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pywinauto import keyboard
from _probe_lib import (sycon_main, bring_front, safe_click, dump, iter_items, project_tree, dismiss_errors,
                        close_menus, wait_menu, popup_menus)

OUT = sys.argv[1] if len(sys.argv) > 1 else "uia_catalog_menus.txt"
main = sycon_main(); pid = main.process_id()
print("errors dismissed:", len(dismiss_errors(pid, 200)), "menus closed:", close_menus())
bring_front(main)
f = open(OUT, "w", encoding="utf-8")

# 1. catalog trees
proj = project_tree(main)
for t in main.descendants(control_type="Tree"):
    if t == proj:
        continue
    print("==== catalog tree auto=", t.element_info.automation_id, t.rectangle(), file=f)
    for it in list(iter_items(t)):
        if it.window_text() in ("PROFINET IO",):
            try:
                it.expand(); time.sleep(1.0)
            except Exception as e:  # noqa: BLE001
                print("  expand failed:", e, file=f)
    dump(t, max_depth=6, out=f)
    # expand the vendor-level nodes under PROFINET IO one level more
    for it in list(iter_items(t)):
        if it.window_text() == "PROFINET IO":
            for v in list(iter_items(it)):
                try:
                    v.expand()
                except Exception:  # noqa: BLE001
                    pass
            time.sleep(1.0)
            print("==== PROFINET IO expanded", file=f)
            dump(it, max_depth=4, out=f)
            try:
                it.collapse()
            except Exception:  # noqa: BLE001
                pass
f.flush()

# 2. main menus
bar = [tb for tb in main.descendants(control_type="ToolBar") if tb.window_text() == "Menu Bar"][0]
buttons = bar.children()
print("menu bar buttons:", [(b.window_text(), b.element_info.control_type) for b in buttons], file=f)
for b in buttons:
    name = b.window_text()
    if not name:
        continue
    close_menus()
    safe_click(b, pid)
    m = wait_menu(8)
    print(f"==== menu {name!r}: popup={bool(m)}", file=f)
    if m:
        dump(m, max_depth=3, out=f)
        # open each submenu entry that has a sub-menu? (skipped: read-only, top level only)
    keyboard.send_keys("{ESC}"); time.sleep(0.5)
close_menus()
f.close()
print("written", OUT)
