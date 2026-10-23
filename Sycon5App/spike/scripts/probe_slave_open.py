"""Step 3a (read-only): with the project open and logged in -
  1. right-click one slave in the netProject tree, dump its context menu, Esc;
  2. list the win32 control classes of the main window;
  3. double-click the slave to open its DTM configuration dialog; dump the new top-level window(s) of SYCON.net
     to <out> (and the main window after the double-click to <out>.main.txt, in case the dialog docks inside it).
The dialog is LEFT OPEN for the next probe (probe_dtm_pages.py) - nothing is saved.

Usage:  python -I scripts/probe_slave_open.py [station-name] [out.txt]
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pywinauto import Desktop, keyboard
from _probe_lib import sycon_main, bring_front, safe_click, dump, station_item, top_windows, popup_menus, desktop

STATION = sys.argv[1] if len(sys.argv) > 1 else "n0030-rc1-xn1"
OUT = sys.argv[2] if len(sys.argv) > 2 else f"uia_dtm_{STATION}.txt"

main = sycon_main()
pid = main.process_id()
print("main:", main.window_text(), "pid", pid)
bring_front(main)
item = station_item(main, STATION)
print("item:", item.window_text(), item.rectangle())

# 1. context menu
safe_click(item, pid, button="right")
time.sleep(1.5)
print("==== popup menus after right-click")
menus = popup_menus()
for w in menus:
    dump(w, max_depth=3)
if not menus:
    print("  (none found as top-level Menu windows)")
keyboard.send_keys("{ESC}")
time.sleep(0.7)

# 2. win32 control classes of the main window
print("==== main window (win32 backend) non-trivial controls")
m32 = Desktop(backend="win32").window(title_re=r"SYCON\.net - \[.*")
for c in m32.descendants():
    cn = c.class_name()
    if cn not in ("Button", "Static", "msctls_statusbar32", "ToolbarWindow32"):
        try:
            print(f"  {cn} | ctrl_id={c.control_id()} | {c.window_text()[:60]!r} | {c.rectangle()}")
        except Exception as e:  # noqa: BLE001
            print("  <err>", e)

# 3. DTM configuration dialog
before = {w.handle for w in top_windows(pid)}
safe_click(item, pid)
time.sleep(0.4)
safe_click(item, pid, double=True)
print("==== waiting for a new top-level SYCON.net window (the DTM dialog)")
new = []
for _ in range(40):
    time.sleep(1.5)
    new = [w for w in top_windows(pid) if w.handle not in before and w.window_text().strip()]
    if new:
        time.sleep(3)  # let the DTM pages load
        new = [w for w in top_windows(pid) if w.handle not in before and w.window_text().strip()]
        break
with open(OUT, "w", encoding="utf-8") as f:
    for w in new:
        print("DLG:", repr(w.window_text()), w.class_name(), w.rectangle())
        print("==== DLG:", repr(w.window_text()), w.class_name(), w.rectangle(), file=f)
        dump(w, max_depth=14, out=f)
with open(OUT + ".main.txt", "w", encoding="utf-8") as f:
    dump(main, max_depth=12, out=f)
print("dumped", len(new), "new window(s) to", OUT, "- main window after the double-click to", OUT + ".main.txt")
