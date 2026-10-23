"""Probe module selection + parameter editing on an OPEN slave dialog with the WIN32 backend for the grid's
in-place editors (they are plain Win32 ComboBox/Edit children of the dialog; UIA pattern calls on them close
the editor). Changes are discarded by the caller (probe_question_no.py).

Usage:  python -I scripts/probe_parameters3.py <station> "<module text>"
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pywinauto import mouse, keyboard, Desktop
from _probe_lib import sycon_main, safe_click, iter_items, config_dialogs

STATION, MODULE = sys.argv[1], sys.argv[2]
main = sycon_main(); pid = main.process_id()
dlg = config_dialogs(pid, STATION)[0]
nav = dlg.descendants(control_type="Tree")[0]
pages = {i.window_text(): i for i in iter_items(nav)}
pages["Modules"].select(); time.sleep(1.5)
grid = [p for p in dlg.descendants(control_type="Pane") if p.element_info.automation_id == "321"][0]
r = grid.rectangle()
d32 = Desktop(backend="win32").window(handle=dlg.handle)


def editors():
    """Win32 children of the dialog that are in-place editors: ComboBox / Edit / SysIPAddress32 with a ctrl id >= 1900."""
    out = {}
    for c in d32.descendants():
        try:
            if c.class_name() in ("ComboBox", "Edit", "SysIPAddress32", "Button") and c.control_id() >= 1900 and c.is_visible():
                out[(c.class_name(), c.control_id())] = c
        except Exception:  # noqa: BLE001
            pass
    return out


def texts(prefix):
    return [t.window_text() for t in dlg.descendants(control_type="Text") if t.window_text().startswith(prefix)]


add = [b for b in dlg.descendants(control_type="Button") if b.window_text() == "Add Module"][0]
safe_click(add, pid); time.sleep(1.5)
print("after Add Module:", texts("Use of slots"), texts("State of data"))
mouse.click(coords=(r.left + 150, r.top + 47)); time.sleep(1.5)
eds = editors()
print("editors after the Module-cell click:", list(eds))
cb = eds.get(("ComboBox", 1904))
if cb:
    print("combo 1904: selected:", repr(cb.selected_text()), "| items:", cb.item_count())
    # close its dropdown without Esc (Esc kills the editor): a win32 CB_SHOWDROPDOWN 0
    import win32con
    cb.send_message(win32con.CB_SHOWDROPDOWN, 0, 0); time.sleep(0.5)
    print("dropdown shown:", cb.send_message(win32con.CB_GETDROPPEDSTATE, 0, 0))
    try:
        cb.select(MODULE); time.sleep(1.0)
        print("win32 select ok -> selected:", repr(cb.selected_text()))
    except Exception as ex:  # noqa: BLE001
        print("win32 select failed:", ex)
    print("editor still alive:", ("ComboBox", 1904) in editors())
# commit: click the slot cell, then verify by re-opening the Module cell
mouse.click(coords=(r.left + 60, r.top + 47)); time.sleep(1.0)
print("after commit:", texts("State of data"), "| editors:", list(editors()))
mouse.click(coords=(r.left + 150, r.top + 47)); time.sleep(1.2)
cb = editors().get(("ComboBox", 1904))
print("re-opened Module cell selected:", repr(cb.selected_text()) if cb else "(no combo)")
if cb:
    import win32con
    cb.send_message(win32con.CB_SHOWDROPDOWN, 0, 0); time.sleep(0.3)
mouse.click(coords=(r.left + 60, r.top + 47)); time.sleep(0.8)
if not config_dialogs(pid, STATION):
    raise SystemExit("dialog closed")
# select the row through a read-only cell (no editor opens there), then the Dataset combo (ctrl id 311)
import win32con
mouse.click(coords=(r.left + 450, r.top + 47)); time.sleep(1.0)
print("editors after read-only cell click:", list(editors()))
c311 = [c for c in d32.descendants(class_name="ComboBox") if c.control_id() == 311][0]
c312 = [c for c in d32.descendants(class_name="ComboBox") if c.control_id() == 312][0]
print(f"combo 311: enabled={c311.is_enabled()} selected={c311.selected_text()!r} items={c311.item_texts()}")
print(f"combo 312: enabled={c312.is_enabled()} selected={c312.selected_text()!r} items={c312.item_texts()}")
if not c311.is_enabled():
    # maybe the DAP row (row 1) has no parameters and the new row must be the selected one: try row 1 too
    mouse.click(coords=(r.left + 450, r.top + 29)); time.sleep(1.0)
    print(f"after row-1 click: combo 311 enabled={c311.is_enabled()} selected={c311.selected_text()!r}")
    mouse.click(coords=(r.left + 450, r.top + 47)); time.sleep(1.0)
    print(f"after row-2 click: combo 311 enabled={c311.is_enabled()} selected={c311.selected_text()!r}")
if c311.is_enabled():
    c311.select("Parameter"); time.sleep(1.5)
    print("Dataset -> Parameter; selected:", repr(c311.selected_text()))
lower = [p for p in dlg.descendants(control_type="Pane") if p.element_info.automation_id == "322"][0]
lr = lower.rectangle()
print("lower grid:", repr(lower.window_text()), lower.class_name(), lr)
for y in (30, 48):
    for x in (20, 100, 200, 300, 400, 500):
        before = set(editors())
        mouse.click(coords=(lr.left + x, lr.top + y)); time.sleep(1.0)
        now = editors()
        new = {k: v for k, v in now.items() if k not in before}
        desc = []
        for k, v in new.items():
            try:
                desc.append((k, v.window_text()[:40] if k[0] != "ComboBox" else (v.selected_text(), v.item_texts()[:8]), str(v.rectangle())))
            except Exception as ex:  # noqa: BLE001
                desc.append((k, f"read failed {ex}"))
        if desc:
            print(f"lower grid click (x+{x}, y+{y}): new editors:", desc)
        if not config_dialogs(pid, STATION):
            print("dialog closed"); break
print("done")
