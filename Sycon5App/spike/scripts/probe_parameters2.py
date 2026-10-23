"""Probe module parameter editing on an OPEN slave dialog (changes discarded): Modules page -> Add Module ->
select a module through the Module cell's in-place ComboBox (UIA select by text), verify it, select the row,
read the 'Dataset' combo, click the lower grid's cells.

Usage:  python -I scripts/probe_parameters2.py <station> "<module text>"
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


def combo(auto):
    c = [e for e in dlg.descendants(control_type="ComboBox") if e.element_info.automation_id == auto]
    return c[0] if c else None


add = [b for b in dlg.descendants(control_type="Button") if b.window_text() == "Add Module"][0]
safe_click(add, pid); time.sleep(1.5)
print("after Add Module:", texts("Use of slots"), texts("State of data"))
mouse.click(coords=(r.left + 150, r.top + 47)); time.sleep(1.5)
c = combo("1904")
print("in-place module combo:", bool(c), "selected before:", repr(c.selected_text()) if c else None,
      "| dropdown open:", any(w.class_name() == "ComboLBox" for w in raw_tops().values()))
try:
    c.select(MODULE); time.sleep(1.5)
    print("select() ok; selected now:", repr(c.selected_text()))
except Exception as ex:  # noqa: BLE001
    print("select() failed:", ex)
    pops = [w for w in raw_tops().values() if w.class_name() == "ComboLBox"]
    lst = desktop().window(handle=pops[0].handle).wrapper_object()
    it = [i for i in lst.children() if i.window_text() == MODULE][0]
    try:
        it.scroll_into_view()
    except Exception as ex2:  # noqa: BLE001
        print("scroll_into_view failed:", ex2)
    time.sleep(0.3)
    it = [i for i in lst.children() if i.window_text() == MODULE][0]
    print("item rect:", it.rectangle())
    it.click_input(); time.sleep(1.5)
    c = combo("1904")
    print("fallback click; selected now:", repr(c.selected_text()) if c else "(combo gone)")
print("after module choice:", texts("Use of slots"), texts("State of data"))
# commit the cell edit by clicking the slot cell of the same row, then verify by re-opening the Module cell
mouse.click(coords=(r.left + 60, r.top + 47)); time.sleep(1.0)
print("after commit click:", texts("State of data"))
mouse.click(coords=(r.left + 150, r.top + 47)); time.sleep(1.2)
c = combo("1904")
print("re-opened Module cell: selected =", repr(c.selected_text()) if c else "(no combo)")
mouse.click(coords=(r.left + 60, r.top + 47)); time.sleep(1.0)
mouse.click(coords=(r.left + 400, r.top + 190)); time.sleep(0.8)   # click on the 'Use of slots' text area: leaves the grid
if not config_dialogs(pid, STATION):
    raise SystemExit("dialog closed")
print("state:", texts("Use of slots"), texts("State of data"))
for auto in ("311", "312"):
    e = combo(auto)
    if e is None:
        print("combo", auto, "missing"); continue
    print(f"combo {auto} {e.window_text()!r} enabled={e.is_enabled()}", end=" ")
    try:
        print("selected=", repr(e.selected_text()), "items=", e.texts())
    except Exception as ex:  # noqa: BLE001
        print("read failed:", ex)
lower = [p for p in dlg.descendants(control_type="Pane") if p.element_info.automation_id == "322"][0]
lr = lower.rectangle()
print("lower grid:", repr(lower.window_text()), lower.class_name(), lr)
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
                print("     Combo selected:", repr(e.selected_text()))
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
