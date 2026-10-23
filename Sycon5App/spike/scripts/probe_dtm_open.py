"""Step 3b (read-only): open the DTM configuration dialog of one slave and dump it (dialog LEFT OPEN).
Opens it via the context menu entry 'Configuration...' (the way the driver will), falling back to a double-click.

Usage:  python -I scripts/probe_dtm_open.py [station-name] [out.txt]
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _probe_lib import (sycon_main, bring_front, safe_click, dump, station_item, top_windows, popup_menus,
                        wait_menu, close_menus, new_dialog)

STATION = sys.argv[1] if len(sys.argv) > 1 else "n0030-rc1-xn1"
OUT = sys.argv[2] if len(sys.argv) > 2 else f"uia_dtm_{STATION}.txt"

main = sycon_main()
pid = main.process_id()
print("main:", main.window_text(), "pid", pid)
print("menus open before:", len(popup_menus()), "-> closed:", close_menus())
bring_front(main)
item = station_item(main, STATION)
print("item:", item.window_text(), item.rectangle())
before = {w.handle for w in top_windows(pid)}

safe_click(item, pid, button="right")
menu = wait_menu(15)
print("context menu:", bool(menu), (menu.rectangle() if menu else None))
if menu:
    conf = [m for m in menu.children() if m.window_text().startswith("Configuration")]
    print("Configuration... item:", [c.window_text() for c in conf])
    safe_click(conf[0], pid, allow_menu=True)
else:
    print("no context menu; double-clicking")
    safe_click(item, pid)
    time.sleep(0.4)
    safe_click(item, pid, double=True)

new = new_dialog(pid, before, timeout=90, settle=4)
with open(OUT, "w", encoding="utf-8") as f:
    for w in new:
        print("DLG:", repr(w.window_text()), w.class_name(), w.rectangle())
        print("==== DLG:", repr(w.window_text()), w.class_name(), w.rectangle(), file=f)
        dump(w, max_depth=14, out=f)
with open(OUT + ".main.txt", "w", encoding="utf-8") as f:
    dump(main, max_depth=12, out=f)
print("dumped", len(new), "new window(s) to", OUT)
