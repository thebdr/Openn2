"""Add one catalog device to the open project by drag-drop, stepwise, with a liveness check after every mouse
action (nothing saved). Optionally start a NEW (untitled, unsaved) project first via File > New (WM_COMMAND).

Usage:  python -I scripts/probe_add_device.py [--new-project] "<catalog path>" <dx> <dy>
  e.g.  python -I scripts/probe_add_device.py --new-project "PROFINET IO/Master/CIFX RE/PNM" 400 42
        python -I scripts/probe_add_device.py "PROFINET IO/Slave/AL1202" 37 520
<dx>,<dy> = drop point relative to the netDevice drawing pane (auto id 3000): the root bus line is at y=42,
the controller's vertical bus line at x=37.
"""
import os, sys, time, datetime, ctypes
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pywinauto import mouse
from _probe_lib import (sycon_main, bring_front, safe_click, iter_items, project_tree, dismiss_errors,
                        close_menus, pid_at_point, top_windows, sycon_pids, user32)

args = [a for a in sys.argv[1:] if not a.startswith("--")]
NEW = "--new-project" in sys.argv
PATH = args[0].split("/") if args else ["PROFINET IO", "Slave", "AL1202"]
# a catalog name may itself contain '/': re-join the tail (e.g. "CIFX RE/PNM")
if len(PATH) > 3:
    PATH = PATH[:2] + ["/".join(PATH[2:])]
DX = int(args[1]) if len(args) > 1 else 37
DY = int(args[2]) if len(args) > 2 else 520
WM_COMMAND, ID_FILE_NEW = 0x0111, 57600
main = sycon_main(); pid = main.process_id()


def tree_nodes():
    try:
        return [i.window_text() for i in iter_items(project_tree(main))]
    except SystemExit:
        return None


def alive(step):
    ok = pid in sycon_pids()
    wins = [w.window_text()[:50] for w in top_windows(pid)] if ok else []
    nodes = tree_nodes() if ok else None
    print(f"{datetime.datetime.now():%H:%M:%S} [{step}] process={ok} windows={wins} nodes={nodes if nodes is None or len(nodes) < 4 else len(nodes)}")
    sys.stdout.flush()
    return ok


def answer_no_to_save_prompt():
    for w in top_windows(pid):
        if w.window_text() in ("SYCON.net", "Save", "Confirm"):
            btns = {b.window_text().replace("&", ""): b for b in w.descendants(control_type="Button")}
            print("  prompt:", [t.window_text() for t in w.descendants(control_type="Text")][:3], "buttons:", list(btns))
            for name in ("No", "Nein"):
                if name in btns:
                    safe_click(btns[name], pid, allow_menu=True); time.sleep(1.0); return True
            raise RuntimeError(f"unexpected prompt {list(btns)}; refusing")
    return False


print("errors dismissed:", len(dismiss_errors(pid, 200)), "menus closed:", close_menus())
if not main.is_enabled():
    raise SystemExit("main window disabled: a modal dialog is open")
bring_front(main)
alive("start")
if NEW:
    user32.PostMessageW(main.handle, WM_COMMAND, ID_FILE_NEW, 0)
    time.sleep(3.0)
    answer_no_to_save_prompt()
    time.sleep(2.0)
    print("  errors:", dismiss_errors(pid, 20))
    main = sycon_main()
    alive("after File>New: " + main.window_text())
before_nodes = tree_nodes() or []
cat = [t for t in main.descendants(control_type="Tree") if t.element_info.automation_id == "40000"][0]
node = None
for name in PATH:
    scope = iter_items(cat) if node is None else iter_items(node)
    node = [i for i in scope if i.window_text() == name][0]
    if name != PATH[-1]:
        node.expand(); time.sleep(0.5)
node.ensure_visible(); time.sleep(0.5)
item = [i for i in iter_items(cat) if i.window_text() == PATH[-1]][0]
print("catalog item:", item.window_text(), item.rectangle())
pane = [p for p in main.descendants(control_type="Pane") if p.element_info.automation_id == "3000"][0]
pr = pane.rectangle()
x, y = pr.left + DX, pr.top + DY
h, owner = pid_at_point(x, y)
buf = ctypes.create_unicode_buffer(256); user32.GetClassNameW(h, buf, 256)
print(f"drop point ({x},{y}): class {buf.value!r} pid {owner} (pane rect {pr})")
if owner != pid:
    raise SystemExit("drop point covered by another process")
src = item.rectangle().mid_point()
safe_click(item, pid); time.sleep(0.5); alive("select catalog item")
mouse.press(coords=(src.x, src.y)); time.sleep(0.4)
mouse.move(coords=(src.x + 5, src.y + 5)); time.sleep(0.2)
mouse.move(coords=(src.x + 15, src.y + 15)); time.sleep(0.4); alive("drag started")
n = 20
for i in range(1, n + 1):
    mouse.move(coords=(src.x + (x - src.x) * i // n, src.y + (y - src.y) * i // n)); time.sleep(0.06)
time.sleep(0.6); alive("over drop point")
mouse.release(coords=(x, y)); time.sleep(1.5); alive("mouse up")
time.sleep(5.0)
if alive("after drop (6.5 s)"):
    print("errors:", dismiss_errors(pid, 20))
    time.sleep(2.0)
    alive("after dismissing errors")
    nodes = tree_nodes() or []
    print("new nodes:", [n_ for n_ in nodes if n_ not in before_nodes])
    for lst in main.descendants(control_type="List"):
        for it in lst.children():
            print("  LOG:", repr(it.window_text()[:220]))
