"""Cloning several stations at once the user's way (2026-10-25: "click on first element in netDevice, then hold
Shift + arrow down to select multiple", then Ctrl+C / Ctrl+V). On a new project from the base project: a controller,
one AL1202 (dropped at pane offsets 602 / 72), one clone through the tree; the project saved into spike/scratch to
read the icons' canvas boxes; then on the canvas (a) click the first icon, Shift+Down, Ctrl+C, Ctrl+V and (b) click
the first icon, Shift+click the second, Ctrl+C, Ctrl+V - two new nodes expected each time. A screenshot of the
SYCON.net window after every step goes to spike/scratch/recordings/_probe_canvas/.
Usage (from Sycon5App, the repo venv):  python -I scripts\\probe_canvas_multiselect.py"""
import os
import sys
import time

import win32gui

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP)
sys.path.insert(0, os.path.join(APP, "scripts"))

from pywinauto import keyboard, mouse               # noqa: E402
from sycon5 import SyconDriver, catalog            # noqa: E402
from sycon5.drawing import drawing_pane            # noqa: E402
from sycon5.readback import read_project           # noqa: E402
from sycon5.session import log                     # noqa: E402
from ui_recorder import png_of_window              # noqa: E402

BASE = os.path.join(APP, "spike", "scratch", "AutomateSyconProj_BaseProj.spj")
SPJ = os.path.join(APP, "spike", "scratch", "_probe_canvas", "Probe.spj")
OUT = os.path.join(APP, "spike", "scratch", "recordings", "_probe_canvas")
os.makedirs(OUT, exist_ok=True)
shot_no = 0


def snap(s, name):
    global shot_no
    shot_no += 1
    path = os.path.join(OUT, "%02d_%s.png" % (shot_no, name))
    png_of_window(s.main().handle, path)
    log("  screenshot", os.path.basename(path))


def paste_selected(s, before, expected, label):
    keyboard.send_keys("^c")
    time.sleep(0.8)
    t0 = time.time()
    keyboard.send_keys("^v")
    new = []
    while time.time() - t0 < 40:
        time.sleep(1.0)
        s.dismiss_errors()
        new = [n for n in s.nodes() if n not in before]
        if len(new) >= expected:
            break
    log("%s: %d new node(s) after %.1f s: %s" % (label, len(new), time.time() - t0,
                                                  [catalog.parse_node(n)["station"] for n in new if catalog.parse_node(n)]))
    snap(s, "after_paste")
    return new


d = SyconDriver()
try:
    d.open(BASE)
    d.new_project()
    d.add_controller("CIFX RE/PNM")
    first = d.add_station("AL1202", kind="slave", gsdml="GSDML-V2.34-ifm-AL1202-20181105.xml")
    second = d.clone_station(first["station"], 1)[0]
    os.makedirs(os.path.dirname(SPJ), exist_ok=True)
    d.save_as(SPJ)
    boxes = {dv.device_no: dv.rect for dv in read_project(SPJ).devices}
    log("canvas boxes:", boxes)
    s = d.session
    s.close_menus()
    s.bring_front()
    r = drawing_pane(s.main()).rectangle()
    log("drawing pane:", (r.left, r.top, r.right, r.bottom))

    def centre(station):
        top, left, bottom, right = boxes[station]
        return (r.left + (left + right) // 2, r.top + (top + bottom) // 2)

    # (a) click the first icon, Shift+Down
    before = s.nodes()
    mouse.click(coords=centre(first["station"]))
    time.sleep(0.8)
    snap(s, "a_clicked_first")
    keyboard.send_keys("+{DOWN}")
    time.sleep(0.8)
    snap(s, "a_shift_down")
    new = paste_selected(s, before, 2, "(a) click + Shift+Down")
    # (b) click the first icon, Shift+click the second
    before = s.nodes()
    mouse.click(coords=centre(first["station"]))
    time.sleep(0.6)
    keyboard.send_keys("{VK_SHIFT down}")
    mouse.click(coords=centre(second["station"]))
    keyboard.send_keys("{VK_SHIFT up}")
    time.sleep(0.8)
    snap(s, "b_shift_click_second")
    paste_selected(s, before, 2, "(b) click + Shift+click")
    time.sleep(1.0)
finally:
    log("close:", d.close())
