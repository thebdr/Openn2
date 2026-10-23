"""Step 4, stepwise (nothing saved): drag one catalog device onto the controller's vertical bus line, checking
after EVERY mouse action that SYCON.net is still alive (process, main window, netProject tree) - to find the
step that kills it. Then opens the new node's 'Configuration...' and dumps the dialog (LEFT OPEN).

Usage:  python -I scripts/probe_catalog_add2.py [catalog-item] [dx] [dy]     (default AL1202 37 520)
"""
import os, sys, time, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pywinauto import mouse, keyboard
from _probe_lib import (sycon_main, bring_front, safe_click, dump, iter_items, project_tree, dismiss_errors,
                        close_menus, wait_menu, pid_at_point, top_windows, new_dialog, sycon_pids, user32)

ITEM = sys.argv[1] if len(sys.argv) > 1 else "AL1202"
DX = int(sys.argv[2]) if len(sys.argv) > 2 else 37
DY = int(sys.argv[3]) if len(sys.argv) > 3 else 520
OUT = f"uia_catalog_add2_{ITEM}.txt"
main = sycon_main(); pid = main.process_id()


def alive(step):
    ok_proc = pid in sycon_pids()
    tree = None
    try:
        tree = [i.window_text() for i in iter_items(project_tree(main))] if ok_proc else None
    except SystemExit:
        tree = "NO TREE"
    wins = [w.window_text()[:50] for w in top_windows(pid)] if ok_proc else []
    print(f"{datetime.datetime.now():%H:%M:%S} [{step}] process={ok_proc} windows={wins} nodes={len(tree) if isinstance(tree, list) else tree}")
    sys.stdout.flush()
    return ok_proc


print("errors dismissed:", len(dismiss_errors(pid, 200)), "menus closed:", close_menus())
if not main.is_enabled():
    raise SystemExit("main window disabled: a modal dialog is open")
bring_front(main)
before_nodes = [i.window_text() for i in iter_items(project_tree(main))]
cat = [t for t in main.descendants(control_type="Tree") if t.element_info.automation_id == "40000"][0]
pn = [i for i in iter_items(cat) if i.window_text() == "PROFINET IO"][0]
pn.expand(); time.sleep(0.5)
slave = [i for i in iter_items(pn) if i.window_text() == "Slave"][0]
slave.expand(); time.sleep(0.5)
item = [i for i in iter_items(slave) if i.window_text() == ITEM][0]
item.ensure_visible(); time.sleep(0.5)
item = [i for i in iter_items(slave) if i.window_text() == ITEM][0]
print("catalog item:", item.window_text(), item.rectangle())
alive("start")
pane = [p for p in main.descendants(control_type="Pane") if p.element_info.automation_id == "3000"][0]
pr = pane.rectangle()
x, y = pr.left + DX, pr.top + DY
h, owner = pid_at_point(x, y)
import ctypes
buf = ctypes.create_unicode_buffer(256); user32.GetClassNameW(h, buf, 256)
print(f"drop point ({x},{y}): hwnd {h} class {buf.value!r} pid {owner} (pane 3000 rect {pr})")
if owner != pid:
    raise SystemExit("drop point covered by another process")
src = item.rectangle().mid_point()

safe_click(item, pid); time.sleep(0.5); alive("select catalog item")
mouse.press(coords=(src.x, src.y)); time.sleep(0.4); alive("mouse down on item")
mouse.move(coords=(src.x + 5, src.y + 5)); time.sleep(0.2)
mouse.move(coords=(src.x + 15, src.y + 15)); time.sleep(0.4); alive("drag started (15px)")
n = 20
for i in range(1, n + 1):
    mouse.move(coords=(src.x + (x - src.x) * i // n, src.y + (y - src.y) * i // n)); time.sleep(0.06)
time.sleep(0.6); alive("moved over drop point")
mouse.release(coords=(x, y)); time.sleep(1.0); alive("mouse up (1 s)")
time.sleep(5.0)
if alive("after drop (6 s)"):
    print("errors:", dismiss_errors(pid, 20))
    nodes = [i.window_text() for i in iter_items(project_tree(main))]
    new = [n_ for n_ in nodes if n_ not in before_nodes]
    print("new nodes:", new)
    for lst in main.descendants(control_type="List"):
        for it in lst.children():
            print("  LOG:", repr(it.window_text()[:220]))
    if new:
        node = [i for i in iter_items(project_tree(main)) if i.window_text() == new[0]][0]
        before = {w.handle for w in top_windows(pid)}
        safe_click(node, pid, button="right")
        m = wait_menu(15)
        conf = [c for c in m.children() if c.window_text().startswith("Configuration")] if m else []
        if conf:
            safe_click(conf[0], pid, allow_menu=True)
            dl = new_dialog(pid, before, timeout=90, settle=4)
            with open(OUT, "w", encoding="utf-8") as f:
                for w in dl:
                    print("DLG:", repr(w.window_text()), w.class_name(), w.rectangle())
                    print("==== DLG:", repr(w.window_text()), w.class_name(), w.rectangle(), file=f)
                    dump(w, max_depth=14, out=f)
            print("written", OUT)
        else:
            close_menus(); print("no Configuration... entry")
