"""Cancel the open DTM configuration dialog(s) (read-only: Cancel discards; never OK/Apply).

Usage:  python -I scripts/probe_cancel_dialog.py [title-substring]
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _probe_lib import sycon_main, safe_click, dismiss_errors, config_dialogs

SUB = sys.argv[1] if len(sys.argv) > 1 else "Configuration"
main = sycon_main(); pid = main.process_id()
for dlg in config_dialogs(pid, SUB):
    btns = {b.window_text().replace("&", ""): (b, b.element_info.automation_id, b.rectangle())
            for b in dlg.descendants(control_type="Button") if b.window_text().replace("&", "") in ("OK", "Cancel", "Apply", "Help")}
    print("dialog:", dlg.window_text()[:70], "buttons:", {k: (v[1], str(v[2])) for k, v in btns.items()})
    if "Cancel" in btns:
        safe_click(btns["Cancel"][0], pid, allow_menu=True)
    else:
        dlg.type_keys("{ESC}", set_foreground=True)
    time.sleep(2.5)
    print("  errors after:", dismiss_errors(pid, 20))
print("dialogs still open:", [d.window_text()[:60] for d in config_dialogs(pid, SUB)], "| main enabled:", sycon_main().is_enabled())
