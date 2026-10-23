"""Open the 'Symbolic Name...' dialog of a netProject node from its context menu, dump it, Cancel it.

Usage:  python -I scripts/probe_symbolic_name.py <station>
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _probe_lib import (sycon_main, bring_front, safe_click, dump, station_item, top_windows, wait_menu,
                        close_menus, new_dialog, dismiss_errors)

STATION = sys.argv[1]
main = sycon_main(); pid = main.process_id()
close_menus(); bring_front(main)
item = station_item(main, STATION)
before = {w.handle for w in top_windows(pid)}
safe_click(item, pid, button="right")
m = wait_menu(15)
entry = [c for c in m.children() if c.window_text().startswith("Symbolic Name")][0]
safe_click(entry, pid, allow_menu=True)
for w in new_dialog(pid, before, timeout=30, settle=1.5):
    print("==== DLG:", repr(w.window_text()), w.class_name(), w.rectangle())
    dump(w, max_depth=6, width=120)
    for e in w.descendants(control_type="Edit"):
        try:
            print("   Edit", repr(e.window_text()), "auto=", e.element_info.automation_id, "readonly=", e.iface_value.CurrentIsReadOnly, "value=", repr(e.get_value()))
        except Exception as ex:  # noqa: BLE001
            print("   Edit read failed:", ex)
    btns = {b.window_text().replace("&", ""): b for b in w.descendants(control_type="Button")}
    if "Cancel" in btns:
        safe_click(btns["Cancel"], pid, allow_menu=True); print("Cancel pressed")
    else:
        w.close(); print("closed")
time.sleep(1.0)
print("errors:", dismiss_errors(pid, 10), "| open:", [w.window_text()[:50] for w in top_windows(pid)])
