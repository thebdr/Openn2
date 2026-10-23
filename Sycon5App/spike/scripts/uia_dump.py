"""Spike: launch SYCON.net (read-only use) and dump what UI Automation exposes."""
import sys, time, subprocess, os
from pywinauto import Desktop, Application
from pywinauto.findwindows import find_elements

EXE = r"C:\Program Files (x86)\Hilscher GmbH\SYCONnet\Syconu.exe"
PROJ = sys.argv[1] if len(sys.argv) > 1 else None
MAX_DEPTH = int(sys.argv[2]) if len(sys.argv) > 2 else 6

def sycon_windows():
    return [w for w in Desktop(backend="uia").windows() if "sycon" in w.window_text().lower() or "sycon" in (w.class_name() or "").lower()]

procs = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Syconu.exe"], capture_output=True, text=True).stdout
if "Syconu.exe" not in procs:
    args = [EXE] + ([PROJ] if PROJ else [])
    print("launching", args)
    subprocess.Popen(args, cwd=os.path.dirname(EXE))
    for _ in range(90):
        time.sleep(2)
        ws = sycon_windows()
        if ws:
            break
else:
    print("already running")
time.sleep(5)
for w in Desktop(backend="uia").windows():
    t = w.window_text()
    if t.strip():
        print("WIN:", repr(t), w.class_name(), w.process_id())
ws = sycon_windows()
if not ws:
    print("no sycon window found"); sys.exit(1)
main = ws[0]
print("==== main:", main.window_text(), main.rectangle())
def dump(el, depth=0):
    if depth > MAX_DEPTH:
        return
    try:
        info = el.element_info
        name = (info.name or "")[:60]
        print("  " * depth + f"{info.control_type} | {name!r} | cls={info.class_name} | auto={info.automation_id} | {info.rectangle}")
        for c in el.children():
            dump(c, depth + 1)
    except Exception as e:
        print("  " * depth + f"<err {e}>")
dump(main)
