"""Probe the in-place editing of the Modules grid of an open slave DTM dialog (changes discarded at the end):
after 'Add Module', try keys and cell clicks and report every NEW top-level window of SYCON.net (including
ComboLBox dropdowns) and every new element under the dialog. Ends with Cancel -> Question -> No.

Usage:  python -I scripts/probe_modules_grid.py <station> [out.txt]
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pywinauto import keyboard, mouse, Desktop
from _probe_lib import sycon_main, safe_click, dump, iter_items, dismiss_errors, config_dialogs, desktop

STATION = sys.argv[1]
OUT = sys.argv[2] if len(sys.argv) > 2 else f"uia_modules_grid_{STATION}.txt"
main = sycon_main(); pid = main.process_id()
dlg = config_dialogs(pid, STATION)[0]
f = open(OUT, "w", encoding="utf-8")
print("==== DIALOG", dlg.window_text(), file=f)
nav = dlg.descendants(control_type="Tree")[0]
pages = {i.window_text(): i for i in iter_items(nav)}
pages["Modules"].select(); time.sleep(1.5)
grid = [p for p in dlg.descendants(control_type="Pane") if p.element_info.automation_id == "321"][0]
r = grid.rectangle()
print("grid rect:", r, file=f)


def raw_tops():
    return {w.handle: w for w in Desktop(backend="win32").windows(process=pid, visible_only=True)
            if w.class_name() not in ("tooltips_class32", "MSCTFIME UI", "IME")}


def snapshot():
    out = set()
    for e in dlg.descendants():
        try:
            inf = e.element_info
            out.add((inf.control_type, (inf.name or "")[:70], inf.automation_id, str(inf.rectangle)))
        except Exception:  # noqa: BLE001
            pass
    return out


def report(label, before, tops_before):
    after = snapshot()
    new = sorted(after - before)
    print(f"\n==== {label}: {len(new)} new elements under the dialog", file=f)
    for t in new[:40]:
        print("   ", t, file=f)
    for h, w in raw_tops().items():
        if h not in tops_before:
            print(f"==== {label}: NEW WINDOW cls={w.class_name()} title={w.window_text()[:60]!r} {w.rectangle()}", file=f)
            try:
                dump(desktop().window(handle=h).wrapper_object(), max_depth=4, out=f, width=120)
            except Exception as e:  # noqa: BLE001
                print("   (uia wrap failed:", e, ")", file=f)
            try:
                for c in w.children():
                    print(f"   child cls={c.class_name()} text={c.window_text()[:80]!r} {c.rectangle()}", file=f)
                if w.class_name() in ("ComboLBox", "ListBox"):
                    print("   items:", w.item_texts()[:60], file=f)
            except Exception as e:  # noqa: BLE001
                print("   (win32 read failed:", e, ")", file=f)
    f.flush()


def slots():
    for t in dlg.descendants(control_type="Text"):
        if t.window_text().startswith("Use of slots"):
            return t.window_text()


before = snapshot(); tops_before = set(raw_tops())
add = [b for b in dlg.descendants(control_type="Button") if b.window_text() == "Add Module"][0]
safe_click(add, pid); time.sleep(2.0)
report("after Add Module (" + str(slots()) + ")", before, tops_before)
def kc(x, y, keys=None, double=False):
    def run():
        if double:
            mouse.double_click(coords=(r.left + x, r.top + y))
        else:
            mouse.click(coords=(r.left + x, r.top + y))
        if keys:
            time.sleep(0.5); keyboard.send_keys(keys)
    return run


actions = []
for y in (47, 62, 80):                                   # rows 2..3 whatever the row height
    for x in (60, 150, 300, 450):
        actions.append((f"click ({x},{y})", kc(x, y)))
for y in (47, 62):
    for x in (150, 300):
        actions.append((f"dblclick ({x},{y})", kc(x, y, double=True)))
for keys in ("{F2}", "%{DOWN}", "{F4}"):
    for y in (47, 62):
        actions.append((f"click (300,{y}) + {keys}", kc(300, y, keys)))
for label, act in actions:
    b = snapshot(); t = set(raw_tops())
    act(); time.sleep(1.2)
    report(label, b, t)
    tops_now = raw_tops()
    if [w for w in tops_now.values() if w.window_text() == "Question"]:
        print("   !! Question box appeared - stopping actions", file=f); break
    if set(tops_now) - t:                                 # something popped up: close it, never confirm
        keyboard.send_keys("{ESC}"); time.sleep(0.8)
    if not config_dialogs(pid, STATION):
        print("   !! dialog closed - stopping", file=f); break
f.close()
print(open(OUT, encoding="utf-8").read())
