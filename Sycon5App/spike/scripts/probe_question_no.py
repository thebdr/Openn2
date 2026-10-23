"""Answer 'No' to SYCON.net's 'Configuration data has been changed. Do you want to save the data?' question
(= discard the dialog's changes), then Cancel any still-open configuration dialog. Read-only in effect.

Usage:  python -I scripts/probe_question_no.py
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _probe_lib import sycon_main, safe_click, dismiss_errors, config_dialogs, top_windows

main = sycon_main(); pid = main.process_id()
for _ in range(3):
    qs = [w for w in top_windows(pid) if w.window_text() == "Question"]
    for q in qs:
        txt = [t.window_text() for t in q.children() if t.element_info.control_type == "Text"]
        btns = {b.window_text().replace("&", ""): b for b in q.children(control_type="Button")}
        print("Question:", txt, "buttons:", list(btns))
        if "No" in btns:
            safe_click(btns["No"], pid, allow_menu=True); time.sleep(1.5); print("  -> No")
    for dlg in config_dialogs(pid):
        btns = {b.window_text().replace("&", ""): b for b in dlg.descendants(control_type="Button") if b.window_text() in ("OK", "Cancel")}
        if "Cancel" in btns:
            print("Cancel on", dlg.window_text()[:60]); safe_click(btns["Cancel"], pid, allow_menu=True); time.sleep(2.0)
    if not [w for w in top_windows(pid) if w.window_text() == "Question"] and not config_dialogs(pid):
        break
print("errors:", dismiss_errors(pid, 20))
print("open:", [(w.window_text()[:60], w.class_name()) for w in top_windows(pid)], "| main enabled:", sycon_main().is_enabled())
