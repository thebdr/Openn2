"""Walk an open DTM configuration dialog (read-only): select every page of its navigation tree through the UIA
SelectionItem pattern (no mouse), dump the page area after each, list the dialog's own buttons; optionally
Cancel the dialog at the end. Never presses OK/Apply.

Usage:  python -I scripts/probe_dialog_pages.py [title-substring] [out.txt] [--cancel]
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _probe_lib import sycon_main, safe_click, dump, iter_items, dismiss_errors, close_menus, config_dialogs

args = [a for a in sys.argv[1:] if not a.startswith("--")]
SUB = args[0] if args else "Configuration"
OUT = args[1] if len(args) > 1 else "uia_dialog_pages.txt"
CANCEL = "--cancel" in sys.argv
main = sycon_main(); pid = main.process_id()
dlgs = config_dialogs(pid, SUB)
if not dlgs:
    raise SystemExit(f"no open dialog with {SUB!r} in its title")
dlg = dlgs[0]
print("dialog:", dlg.window_text(), dlg.rectangle())
f = open(OUT, "w", encoding="utf-8")
print("==== DIALOG:", repr(dlg.window_text()), dlg.rectangle(), file=f)
print("buttons of the dialog itself:", [(b.window_text(), b.element_info.automation_id, b.rectangle())
                                       for b in dlg.children(control_type="Button")], file=f)
trees = dlg.descendants(control_type="Tree")
nav = trees[0]
print("nav tree auto=", nav.element_info.automation_id, file=f)
hosts = [p for p in dlg.descendants(control_type="Pane") if p.element_info.automation_id == "59649"]
host = hosts[0] if hosts else dlg
items = list(iter_items(nav))
for i, it in enumerate(items):
    name = it.window_text()
    kids = list(iter_items(it))
    try:
        it.select()
    except Exception as e:  # noqa: BLE001
        try:
            safe_click(it, pid)
        except Exception as e2:  # noqa: BLE001
            print(f"==== PAGE {name!r}: cannot select ({e}; {e2})", file=f); continue
    time.sleep(2.0)
    errs = dismiss_errors(pid, 20)
    print(f"\n==== PAGE {name!r} (children: {[k.window_text() for k in kids]}) errors={errs}", file=f)
    dump(host, max_depth=12, out=f, width=160)
    f.flush()
    print("page", name, "dumped")
if CANCEL:
    btns = {b.window_text().replace("&", ""): b for b in dlg.descendants(control_type="Button")
            if b.window_text().replace("&", "") in ("OK", "Cancel", "Apply", "Help")}
    if "Cancel" in btns:
        safe_click(btns["Cancel"], pid, allow_menu=True)
        time.sleep(2.0)
        print("Cancel pressed; still open:", bool(config_dialogs(pid, SUB)), "errors:", dismiss_errors(pid, 20))
    else:
        print("no Cancel button:", list(btns))
f.close()
print("written", OUT)
