"""Clean-up (read-only): dismiss Error boxes, close popup menus, and Cancel/close any other SYCON.net top-level
window that is not the main window. Prints the Output window log. Never saves.

Usage:  python -I scripts/probe_close_dialog.py
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _probe_lib import sycon_main, safe_click, dismiss_errors, close_menus, top_windows

main = sycon_main(); pid = main.process_id()
print("errors dismissed:", dismiss_errors(pid, 200))
print("menus closed:", close_menus())
for w in top_windows(pid):
    t = w.window_text()
    if not t.strip() or t.startswith("SYCON.net - ["):
        continue
    btns = {b.window_text().replace("&", ""): b for b in w.descendants(control_type="Button")}
    print("other window:", repr(t), w.class_name(), "buttons:", list(btns)[:12])
    for name in ("Cancel", "Close", "Abbrechen"):
        if name in btns:
            safe_click(btns[name], pid, allow_menu=True); print("  ->", name, "clicked"); break
    else:
        w.close(); print("  -> WM_CLOSE sent")
    time.sleep(1.5)
print("errors dismissed after:", dismiss_errors(pid, 200))
print("SYCON windows:", [(w.window_text(), w.class_name()) for w in top_windows(pid) if w.window_text().strip()])
for lst in main.descendants(control_type="List"):
    for it in lst.children():
        print("  LOG:", repr(it.window_text()[:220]))
