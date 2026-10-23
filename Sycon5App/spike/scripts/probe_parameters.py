"""Probe module parameter editing on an OPEN slave dialog (changes discarded): Modules page -> Add Module ->
pick a module from the Module cell's dropdown -> read the 'Dataset' combo -> click the lower grid's cells.

Usage:  python -I scripts/probe_parameters.py <station> "<module text prefix>"
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pywinauto import keyboard, mouse, Desktop
from _probe_lib import sycon_main, safe_click, iter_items, config_dialogs, desktop

STATION, MODULE = sys.argv[1], sys.argv[2]
main = sycon_main(); pid = main.process_id()
dlg = config_dialogs(pid, STATION)[0]
nav = dlg.descendants(control_type="Tree")[0]
pages = {i.window_text(): i for i in iter_items(nav)}
pages["Modules"].select(); time.sleep(1.5)
grid = [p for p in dlg.descendants(control_type="Pane") if p.element_info.automation_id == "321"][0]
r = grid.rectangle()


def raw_tops():
    return {w.handle: w for w in Desktop(backend="win32").windows(process=pid, visible_only=True)
            if w.class_name() not in ("tooltips_class32", "MSCTFIME UI", "IME")}


def texts(prefix):
    return [t.window_text() for t in dlg.descendants(control_type="Text") if t.window_text().startswith(prefix)]


add = [b for b in dlg.descendants(control_type="Button") if b.window_text() == "Add Module"][0]
safe_click(add, pid); time.sleep(1.5)
print("after Add Module:", texts("Use of slots"), texts("State of data"))
t0 = set(raw_tops())
mouse.click(coords=(r.left + 150, r.top + 47)); time.sleep(1.5)
pop = [w for h, w in raw_tops().items() if h not in t0 and w.class_name() == "ComboLBox"]
print("module dropdown:", bool(pop))
lst = desktop().window(handle=pop[0].handle).wrapper_object()
items = [i for i in lst.children() if i.window_text().startswith(MODULE)]
print("matching items:", [i.window_text() for i in items][:3])
it = items[0]
try:
    it.scroll_into_view()
except Exception:  # noqa: BLE001
    pass
try:
    it.select(); time.sleep(0.8)
except Exception as ex:  # noqa: BLE001
    print("select() failed:", ex)
if [w for h, w in raw_tops().items() if h not in t0 and w.class_name() == "ComboLBox"]:
    print("list still open -> clicking the item")
    it.click_input(); time.sleep(1.0)
print("list still open after click:", bool([w for h, w in raw_tops().items() if h not in t0 and w.class_name() == "ComboLBox"]))
time.sleep(1.0)
print("after module choice:", texts("Use of slots"), texts("State of data"))
# the Module cell's combo (auto 1904) may still be the in-place editor: read its text
for e in dlg.descendants(control_type="ComboBox"):
    try:
        print(f"ComboBox auto={e.element_info.automation_id} name={e.window_text()!r} selected={e.selected_text()!r} n_items={len(e.texts())}")
    except Exception as ex:  # noqa: BLE001
        print(f"ComboBox auto={e.element_info.automation_id}: read failed {ex}")
# click the row (slot cell) to select it, then read the Dataset combo
mouse.click(coords=(r.left + 60, r.top + 47)); time.sleep(1.0)
keyboard.send_keys("{ESC}"); time.sleep(0.5)      # closes the slot combo editor only (dialog Esc would need focus on the dialog)
if not config_dialogs(pid, STATION):
    raise SystemExit("dialog closed")
for e in dlg.descendants(control_type="ComboBox"):
    if e.element_info.automation_id in ("311", "312"):
        print(f"ComboBox auto={e.element_info.automation_id} {e.window_text()!r}: selected={e.selected_text()!r} items={e.texts()}")
lower = [p for p in dlg.descendants(control_type="Pane") if p.element_info.automation_id == "322"][0]
lr = lower.rectangle()
print("lower grid:", lower.window_text(), lower.class_name(), lr)
for x in (20, 100, 200, 300, 400, 500):
    before = {(e.element_info.control_type, e.element_info.automation_id, str(e.element_info.rectangle)) for e in dlg.descendants()}
    t = set(raw_tops())
    mouse.click(coords=(lr.left + x, lr.top + 30)); time.sleep(1.2)
    new = [e for e in dlg.descendants() if (e.element_info.control_type, e.element_info.automation_id, str(e.element_info.rectangle)) not in before]
    print(f"lower grid click x+{x}: new:", [(e.element_info.control_type, e.element_info.automation_id, e.window_text()[:40]) for e in new][:8])
    for e in new:
        try:
            if e.element_info.control_type == "Edit":
                print("     Edit value:", repr(e.get_value()))
            elif e.element_info.control_type == "ComboBox":
                print("     Combo:", repr(e.selected_text()), e.texts()[:10])
        except Exception as ex:  # noqa: BLE001
            print("     read failed:", ex)
    popped = [w for h, w in raw_tops().items() if h not in t]
    for w in popped:
        print("     NEW WINDOW", w.class_name(), repr(w.window_text()[:40]), w.rectangle())
        try:
            if w.class_name() == "ComboLBox":
                print("     items:", w.item_texts()[:20])
        except Exception:  # noqa: BLE001
            pass
    if popped:
        keyboard.send_keys("{ESC}"); time.sleep(0.5)
    if not config_dialogs(pid, STATION):
        print("dialog closed"); break
