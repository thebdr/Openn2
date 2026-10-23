"""Probe the in-place editors of a custom grid on a page of an OPEN configuration dialog: click cells of one row
at several x offsets and report every new element under the dialog and every new top-level window (dropdowns).
Popups are closed with Esc; nothing is confirmed. The dialog is left open.

Usage:  python -I scripts/probe_grid_cells.py <title-substring> <page> <grid auto-id> <row y offset> <x offsets csv> [out.txt]
  e.g.  python -I scripts/probe_grid_cells.py "Configuration CIFX_RE_PNM" "Device Table" 210 30 20,60,120,200,300,400,500
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pywinauto import keyboard, mouse, Desktop
from _probe_lib import sycon_main, dump, iter_items, config_dialogs, desktop

SUB, PAGE, GRID, Y = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
XS = [int(x) for x in sys.argv[5].split(",")]
OUT = sys.argv[6] if len(sys.argv) > 6 else f"uia_grid_{PAGE.replace(' ', '_').replace('/', '')}.txt"
main = sycon_main(); pid = main.process_id()
dlg = config_dialogs(pid, SUB)[0]
f = open(OUT, "w", encoding="utf-8")
print("==== DIALOG", dlg.window_text(), "PAGE", PAGE, file=f)
nav = dlg.descendants(control_type="Tree")[0]
[i for i in iter_items(nav) if i.window_text() == PAGE][0].select(); time.sleep(2.0)
grid = [p for p in dlg.descendants(control_type="Pane") if p.element_info.automation_id == GRID][0]
r = grid.rectangle()
print("grid:", grid.window_text(), grid.class_name(), r, file=f)


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


for x in XS:
    b = snapshot(); t = set(raw_tops())
    mouse.click(coords=(r.left + x, r.top + Y)); time.sleep(1.2)
    new = sorted(snapshot() - b)
    print(f"\n==== click (x+{x}, y+{Y}): {len(new)} new elements", file=f)
    for e in new[:25]:
        print("   ", e, file=f)
    for e in dlg.descendants():
        try:
            inf = e.element_info
            key = (inf.control_type, (inf.name or "")[:70], inf.automation_id, str(inf.rectangle))
            if key in new:
                if inf.control_type == "Edit":
                    print(f"      value of Edit auto={inf.automation_id}: {e.get_value()!r} readonly={e.iface_value.CurrentIsReadOnly}", file=f)
                elif inf.control_type == "ComboBox":
                    print(f"      ComboBox auto={inf.automation_id}: selected={e.selected_text()!r} items={e.texts()[:15]}", file=f)
                elif inf.control_type == "CheckBox":
                    print(f"      CheckBox auto={inf.automation_id}: state={e.get_toggle_state()}", file=f)
        except Exception as ex:  # noqa: BLE001
            print("      (read failed:", ex, ")", file=f)
    popped = False
    for h, w in raw_tops().items():
        if h not in t:
            popped = True
            print(f"   NEW WINDOW cls={w.class_name()} title={w.window_text()[:60]!r} {w.rectangle()}", file=f)
            try:
                if w.class_name() in ("ComboLBox", "ListBox"):
                    print("   items:", w.item_texts()[:40], file=f)
            except Exception as e:  # noqa: BLE001
                print("   (read failed:", e, ")", file=f)
    if popped:
        keyboard.send_keys("{ESC}"); time.sleep(0.6)
    if not config_dialogs(pid, SUB):
        print("   !! dialog closed - stopping", file=f); break
f.close()
print(open(OUT, encoding="utf-8").read())
