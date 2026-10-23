"""Spike step 3 (read-only): with the project open and logged in -
  1. right-click one base slave in the netProject tree and dump its context menu,
  2. dump the device catalog tree (top level),
  3. list the win32 control classes of the main window (what is NOT UIA-friendly),
  4. double-click the slave to open its DTM configuration dialog and dump the dialog tree
     to uia_dtm_dialog.txt (name / IP / modules / parameters live there).
Everything is escaped or left open for you to Cancel; nothing is saved.

Usage:  python -I uia_probe.py [station-name]      (default n0030-rc1-xn1 = the IFM AL1202 base slave)
"""
import sys, time
from pywinauto import Desktop, keyboard

STATION = sys.argv[1] if len(sys.argv) > 1 else "n0030-rc1-xn1"
d = Desktop(backend="uia")
main = [w for w in d.windows() if w.window_text().startswith("SYCON.net - [")][0]
print("main:", main.window_text())


def dump(el, depth=0, max_depth=8, out=sys.stdout):
    if depth > max_depth:
        return
    try:
        info = el.element_info
        name = (info.name or "")[:90]
        print("  " * depth + f"{info.control_type} | {name!r} | cls={info.class_name} | auto={info.automation_id} | {info.rectangle}", file=out)
        for c in el.children():
            dump(c, depth + 1, max_depth, out)
    except Exception as e:
        print("  " * depth + f"<err {e}>", file=out)


def all_items(el):
    out = []
    for c in el.children():
        if c.element_info.control_type == "TreeItem":
            out.append(c)
        out.extend(all_items(c))
    return out


# the main window holds TWO trees: the device catalog (AS-i, CANopen, ...) and the netProject tree
trees = main.descendants(control_type="Tree")
for t in trees:
    print("TREE:", t.element_info.automation_id, t.rectangle(), [i.window_text()[:40] for i in all_items(t)[:3]])
proj = [t for t in trees if any(i.window_text().startswith("Project:") for i in all_items(t))]
cat = [t for t in trees if t not in proj]
print("==== catalog tree (as expanded now)")
for t in cat:
    dump(t, max_depth=3)
tree = proj[0]
items = all_items(tree)
print("tree items:", len(items))
slave = [i for i in items if f"<{STATION}>" in i.window_text()][0]
print("slave item:", slave.window_text())

# 1. context menu
slave.click_input(button="right")
time.sleep(1.5)
print("==== popup menus after right-click")
for w in d.windows():
    if w.element_info.control_type == "Menu" or w.class_name() == "#32768":
        dump(w, max_depth=3)
keyboard.send_keys("{ESC}")
time.sleep(0.5)

# 2. win32 view of the main window: control classes
print("==== main window (win32 backend) non-trivial controls")
m32 = Desktop(backend="win32").window(title_re=r"SYCON\.net - \[.*")
for c in m32.descendants():
    cn = c.class_name()
    if cn not in ("Button", "Static", "msctls_statusbar32", "ToolbarWindow32"):
        try:
            print(f"  {cn} | ctrl_id={c.control_id()} | {c.window_text()[:60]!r} | {c.rectangle()}")
        except Exception as e:
            print("  <err>", e)

# 3. DTM configuration dialog
slave.click_input()
time.sleep(0.5)
before = {w.handle for w in d.windows()}
slave.double_click_input()
print("==== waiting for a new top-level window (the DTM dialog)")
dlg = None
for _ in range(40):
    time.sleep(1.5)
    new = [w for w in d.windows() if w.handle not in before and w.window_text().strip()]
    if new:
        dlg = new[0]
        break
if dlg:
    print("DLG:", repr(dlg.window_text()), dlg.class_name(), dlg.rectangle())
    time.sleep(3)
    with open("uia_dtm_dialog.txt", "w", encoding="utf-8") as f:
        dump(dlg, max_depth=12, out=f)
    print("dumped to uia_dtm_dialog.txt - Cancel the dialog by hand when done")
else:
    print("no dialog appeared (check whether it opened inside the main window: re-run uia_login_dump.py 10)")
