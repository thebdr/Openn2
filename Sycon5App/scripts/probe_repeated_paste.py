"""After ONE copy of a station in the netProject tree, does every further Ctrl+V paste another clone (the clipboard
keeps the node) - and how fast? On a new project from the base project: a controller, one AL1202 from the catalog,
then: select it, Ctrl+C, Ctrl+V three times each awaited by the tree growing by one; the new nodes and the seconds
per paste are logged. Nothing saved. Usage (from Sycon5App, the repo venv):  python -I scripts\\probe_repeated_paste.py"""
import os
import sys
import time

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP)

from pywinauto import keyboard                      # noqa: E402
from sycon5 import SyconDriver, catalog            # noqa: E402
from sycon5.session import log                     # noqa: E402

BASE = os.path.join(APP, "spike", "scratch", "AutomateSyconProj_BaseProj.spj")
PASTES = 3

d = SyconDriver()
try:
    d.open(BASE)
    d.new_project()
    d.add_controller("CIFX RE/PNM")
    first = d.add_station("AL1202", kind="slave", gsdml="GSDML-V2.34-ifm-AL1202-20181105.xml")
    s = d.session
    s.close_menus()
    s.bring_front()
    d._select_station(first["station"])
    keyboard.send_keys("^c")
    time.sleep(0.8)
    before = s.nodes()
    count = len(before)
    for k in range(PASTES):
        t0 = time.time()
        keyboard.send_keys("^v")
        grown = False
        while time.time() - t0 < 30:
            time.sleep(0.5)
            s.dismiss_errors()
            now = s.nodes()
            if len(now) > count:
                count = len(now)
                grown = True
                break
        log("paste %d: %s after %.1f s" % (k + 1, "a node appeared" if grown else "NOTHING appeared", time.time() - t0))
        if not grown:
            break
    new = [catalog.parse_node(n) for n in s.nodes() if n not in before]
    log("new nodes:", [(n["station"], n["type"]) for n in new if n])
    time.sleep(1.0)
finally:
    log("close:", d.close())
