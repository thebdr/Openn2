"""Probe the Modules page of an open slave DTM dialog (read-only, dialog Cancelled at the end):
  1. General page: are 'Name of station' / IP edits enabled and writable (UIA ValuePattern)?
  2. Modules page: click 'Add Module', dump what appears (new windows / new elements under the dialog), Esc;
  3. click the first data row of the modules grid, dump what appears (in-place editor?), Esc.

Usage:  python -I scripts/probe_modules_page.py <station> [out.txt]
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pywinauto import keyboard
from _probe_lib import (sycon_main, safe_click, dump, iter_items, dismiss_errors, config_dialogs, top_windows,
                        close_menus)

STATION = sys.argv[1]
OUT = sys.argv[2] if len(sys.argv) > 2 else f"uia_modules_{STATION}.txt"
main = sycon_main(); pid = main.process_id()
dlg = config_dialogs(pid, STATION)[0]
f = open(OUT, "w", encoding="utf-8")
print("==== DIALOG", dlg.window_text(), file=f)
nav = dlg.descendants(control_type="Tree")[0]
pages = {i.window_text(): i for i in iter_items(nav)}


def snapshot():
    out = set()
    for e in dlg.descendants():
        try:
            inf = e.element_info
            out.add((inf.control_type, (inf.name or "")[:60], inf.automation_id, str(inf.rectangle)))
        except Exception:  # noqa: BLE001
            pass
    return out


def report_new(label, before, wins_before):
    after = snapshot()
    print(f"\n==== {label}: new elements under the dialog:", file=f)
    for t in sorted(after - before):
        print("   ", t, file=f)
    print(f"==== {label}: gone elements:", len(before - after), file=f)
    for w in top_windows(pid):
        if w.handle not in wins_before:
            print(f"==== {label}: NEW WINDOW {w.window_text()!r} {w.class_name()} {w.rectangle()}", file=f)
            dump(w, max_depth=6, out=f, width=120)
    f.flush()


# 1. General page - editability
pages["General"].select(); time.sleep(1.5)
for e in dlg.descendants(control_type="Edit"):
    try:
        ro = e.iface_value.CurrentIsReadOnly
    except Exception:  # noqa: BLE001
        ro = "?"
    print(f"Edit {e.window_text()!r} auto={e.element_info.automation_id} enabled={e.is_enabled()} readonly={ro} value={e.get_value()!r}", file=f)
for e in dlg.descendants(control_type="CheckBox"):
    print(f"CheckBox {e.window_text()!r} auto={e.element_info.automation_id} enabled={e.is_enabled()} state={e.get_toggle_state()}", file=f)

# 2. Modules page - Add Module
pages["Modules"].select(); time.sleep(1.5)
grid = [p for p in dlg.descendants(control_type="Pane") if p.element_info.automation_id == "321"][0]
print("\nmodules grid:", grid.rectangle(), "class", grid.class_name(), file=f)
for b in dlg.descendants(control_type="Button"):
    if b.window_text() in ("Add Module", "Add Submodule", "Remove"):
        print(f"button {b.window_text()!r} enabled={b.is_enabled()}", file=f)
before = snapshot(); wins_before = {w.handle for w in top_windows(pid)}
add = [b for b in dlg.descendants(control_type="Button") if b.window_text() == "Add Module"][0]
safe_click(add, pid); time.sleep(2.0)
report_new("after Add Module", before, wins_before)
keyboard.send_keys("{ESC}"); time.sleep(1.0); close_menus()
report_new("after Esc", before, wins_before)
for t in dlg.descendants(control_type="Text"):
    if t.window_text().startswith("Use of slots"):
        print("slots:", t.window_text(), file=f)

# 3. click the first data row of the grid (header ~ 20 px, rows ~ 18 px)
r = grid.rectangle()
before = snapshot(); wins_before = {w.handle for w in top_windows(pid)}
from pywinauto import mouse
mouse.click(coords=(r.left + 200, r.top + 30)); time.sleep(1.5)
report_new("after click on grid row 1 (x+200,y+30)", before, wins_before)
mouse.click(coords=(r.left + 350, r.top + 30)); time.sleep(1.5)
report_new("after click on grid row 1 (x+350,y+30)", before, wins_before)
keyboard.send_keys("{ESC}"); time.sleep(0.8)

# Cancel
btns = {b.window_text().replace("&", ""): b for b in dlg.descendants(control_type="Button") if b.window_text() in ("OK", "Cancel")}
safe_click(btns["Cancel"], pid, allow_menu=True); time.sleep(2.0)
print("\nCancelled; still open:", bool(config_dialogs(pid, STATION)), "errors:", dismiss_errors(pid, 20), file=f)
f.close()
print(open(OUT, encoding="utf-8").read())
