"""Step 4 (NOT read-only for the in-memory project, nothing saved): add one device from the device catalog -
  1. right-click the catalog item and dump its context menu (Esc),
  2. drag the catalog item onto the bus line of the netDevice drawing (several drop heights until the netProject
     tree shows a new node),
  3. open the new node's 'Configuration...' and dump the dialog (LEFT OPEN).

Usage:  python -I scripts/probe_catalog_add.py [catalog-item] [out.txt]     (default AL1202)
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pywinauto import mouse, keyboard
from _probe_lib import (sycon_main, bring_front, safe_click, dump, iter_items, project_tree, dismiss_errors,
                        close_menus, wait_menu, pid_at_point, top_windows, new_dialog)

ITEM = sys.argv[1] if len(sys.argv) > 1 else "AL1202"
OUT = sys.argv[2] if len(sys.argv) > 2 else f"uia_catalog_add_{ITEM}.txt"
main = sycon_main(); pid = main.process_id()
print("errors dismissed:", len(dismiss_errors(pid, 200)), "menus closed:", close_menus())
if not main.is_enabled():
    raise SystemExit("main window disabled: a modal dialog is open (probe_cancel_dialog.py first)")
bring_front(main)
proj = project_tree(main)
before_nodes = [i.window_text() for i in iter_items(proj)]
cat = [t for t in main.descendants(control_type="Tree") if t.element_info.automation_id == "40000"][0]
pn = [i for i in iter_items(cat) if i.window_text() == "PROFINET IO"][0]
pn.expand(); time.sleep(0.5)
slave = [i for i in iter_items(pn) if i.window_text() == "Slave"][0]
slave.expand(); time.sleep(0.5)
item = [i for i in iter_items(slave) if i.window_text() == ITEM][0]
item.ensure_visible(); time.sleep(0.5)
item = [i for i in iter_items(slave) if i.window_text() == ITEM][0]
print("catalog item:", item.window_text(), item.rectangle())
f = open(OUT, "w", encoding="utf-8")

# 1. catalog item context menu
safe_click(item, pid, button="right")
m = wait_menu(8)
print("==== catalog item context menu:", bool(m), file=f)
if m:
    dump(m, max_depth=3, out=f)
keyboard.send_keys("{ESC}"); time.sleep(0.5); close_menus()
f.flush()

# 2. drag-drop onto the bus line
pane = [p for p in main.descendants(control_type="Pane") if p.element_info.automation_id == "3000"][0]
pr = pane.rectangle()
print("netDevice drawing pane:", pr, file=f)
src = item.rectangle().mid_point()
added = None
# the controller's PROFINET network is drawn as a VERTICAL bus line at drawing x=35..39 (SYCON_net.xml:
# <PositionRect top="25" left="35" bottom="1010" right="39"/> under the controller); slaves hang off it to the
# right at increasing y. The drawing origin is the pane's client origin at 100 % zoom - so drop a slave there.
for dx, dy in ((37, 520), (37, 560), (36, 500), (38, 600), (37, 650), (35, 520), (39, 520), (37, 700), (37, 800)):
    x, y = pr.left + dx, pr.top + dy
    h, owner = pid_at_point(x, y)
    if owner != pid:
        print(f"drop point ({x},{y}) covered by pid {owner}; skipped", file=f); continue
    wins_before = {w.handle for w in top_windows(pid)}
    safe_click(item, pid)                      # select the catalog item first
    time.sleep(0.3)
    mouse.press(coords=(src.x, src.y)); time.sleep(0.3)
    for i in range(1, 16):                     # intermediate moves for OLE drag-drop
        mouse.move(coords=(src.x + (x - src.x) * i // 15, src.y + (y - src.y) * i // 15)); time.sleep(0.08)
    time.sleep(0.5)
    mouse.release(coords=(x, y)); time.sleep(4.0)
    dismiss = dismiss_errors(pid, 20)
    new_wins = [w.window_text()[:60] for w in top_windows(pid) if w.handle not in wins_before]
    nodes = [i.window_text() for i in iter_items(project_tree(main))]
    new = [n for n in nodes if n not in before_nodes]
    print(f"drop at ({dx},{dy}): errors={dismiss} new windows={new_wins} new nodes={new}", file=f); f.flush()
    if new:
        added = new[0]; break
print("added:", added)
print("==== added node:", added, file=f)
if added:
    for lst in main.descendants(control_type="List"):
        for it in lst.children():
            print("  LOG:", repr(it.window_text()[:220]), file=f)
    # 3. open its Configuration...
    node = [i for i in iter_items(project_tree(main)) if i.window_text() == added][0]
    before = {w.handle for w in top_windows(pid)}
    safe_click(node, pid, button="right")
    m = wait_menu(15)
    conf = [c for c in m.children() if c.window_text().startswith("Configuration")] if m else []
    if conf:
        safe_click(conf[0], pid, allow_menu=True)
        new = new_dialog(pid, before, timeout=90, settle=4)
        for w in new:
            print("DLG:", repr(w.window_text()), w.class_name(), w.rectangle())
            print("==== DLG:", repr(w.window_text()), w.class_name(), w.rectangle(), file=f)
            dump(w, max_depth=14, out=f)
    else:
        print("no Configuration... entry", file=f); close_menus()
f.close()
print("written", OUT)
