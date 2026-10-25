"""Does the netProject tree copy SEVERAL selected stations at once (user 2026-10-25: "i usually double the existing
stations (1->2->4->8->...) by selecting and copy-pasting more than one station at a time")? On a new project from the
base project: a controller, one AL1202 from the catalog, one clone; then the two selected (click, Shift+click and,
if that selects nothing, Ctrl+click), Ctrl+C, the first clicked, Ctrl+V - the tree before and after is logged.
Nothing saved. Usage (from Sycon5App, the repo venv):  python -I scripts\\probe_multiselect_clone.py"""
import os
import sys
import time

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP)

from pywinauto import keyboard, mouse               # noqa: E402
from sycon5 import SyconDriver, catalog            # noqa: E402
from sycon5.session import log                     # noqa: E402

BASE = os.path.join(APP, "spike", "scratch", "AutomateSyconProj_BaseProj.spj")


def centre(item):
    r = item.rectangle()
    return ((r.left + r.right) // 2, (r.top + r.bottom) // 2)


d = SyconDriver()
try:
    d.open(BASE)
    d.new_project()
    d.add_controller("CIFX RE/PNM")
    first = d.add_station("AL1202", kind="slave", gsdml="GSDML-V2.34-ifm-AL1202-20181105.xml")
    second = d.clone_station(first["station"], 1)[0]
    s = d.session
    s.close_menus()
    s.bring_front()
    before = s.nodes()
    log("tree before:", [n for n in before if "<" in n])
    for way in ("shift", "ctrl"):
        a, b = s.station_item(first["station"]), s.station_item(second["station"])
        a.ensure_visible()
        mouse.click(coords=centre(a))
        time.sleep(0.5)
        b.ensure_visible()
        keyboard.send_keys("{VK_SHIFT down}" if way == "shift" else "{VK_CONTROL down}")
        mouse.click(coords=centre(b))
        keyboard.send_keys("{VK_SHIFT up}" if way == "shift" else "{VK_CONTROL up}")
        time.sleep(0.6)
        selected = []
        for it in (a, b):
            try:
                selected.append(it.is_selected())
            except Exception as ex:  # noqa: BLE001
                selected.append("(%s)" % type(ex).__name__)
        log("%s+click: selected states" % way, selected)
        keyboard.send_keys("^c")
        time.sleep(0.8)
        mouse.click(coords=centre(s.station_item(first["station"])))
        time.sleep(0.4)
        keyboard.send_keys("^v")
        t0 = time.time()
        new = []
        while time.time() - t0 < 40:
            time.sleep(1.0)
            s.dismiss_errors()
            new = [n for n in s.nodes() if n not in before]
            if new and len(new) >= 2:
                break
        log("%s+click paste produced %d node(s): %s" % (way, len(new), [catalog.parse_node(n)["station"] for n in new if catalog.parse_node(n)]))
        before = s.nodes()
        if len(new) >= 2:
            break
finally:
    log("close:", d.close())
