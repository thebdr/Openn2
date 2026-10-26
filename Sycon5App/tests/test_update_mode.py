"""The update mode and the controller's name of station (user 2026-10-26: "update an already existing sycon project,
like OP5 did by skipping existing nodes with matching pn name"; "no pn name was set for the controller"), without
SYCON.net: the verification's new controller checks (name, IP, the export's controller name), the update's NOTEs
(a station the project has is skipped, a node the table lacks is kept, a named controller is left), the canvas
writing the new stations alone with the bus reaching the lowest device, the workspace's update command and the
GUI's Update button."""
import importlib.util
import os
import sys
import time

import pytest
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)
from sycon5 import canvas, consumer, exports  # noqa: E402
from sycon5 import workspace as ws  # noqa: E402
from sycon5.handoff import Handoff  # noqa: E402
from sycon5.readback import Device, Project  # noqa: E402
from test_workspace import fake_production  # noqa: E402


def station(name, ip, symbolic="", fld=""):
    return {"role": "slave", "station_name": name, "catalog_kind": "slave", "catalog_item": "AL1202", "model_id": "AL1202",
            "gsdml": "", "ip_address": ip, "subnet_mask": "255.255.255.0", "gateway": "", "update_time_ms": "", "comment": "",
            "symbolic_name": symbolic, "fld": fld}


def device(name, ip, type_name="AL1202"):
    return Device(device_no=name, symbolic="", prog_id="x.PNIOSlave", gsdml="", name=name, ip=ip, type_name=type_name,
                  manufacturer_id=1, device_type_id=2)


def controller(name, ip, network):
    return Device(device_no=name, symbolic="", prog_id="x.PNIOController", gsdml="", name=name, ip=ip, network=list(network))


def handoff_of(stations, ctrl_name="n0001-c", ctrl_ip="192.168.1.1"):
    return Handoff(folder="", controller={"station_name": ctrl_name, "ip_address": ctrl_ip}, stations=stations)


def lines(v, head):
    return [ln for ln in v.lines if ln.startswith(head)]


# ---- the controller's name and address in the verification ----------------------------------------------------- #
def test_the_controllers_name_and_ip_are_checked():
    h = handoff_of([station("n0002-a", "192.168.1.2")])
    good = Project(path="", devices=[controller("n0001-c", "192.168.1.1", [("n0002-a", "192.168.1.2")]), device("n0002-a", "192.168.1.2")])
    v = consumer.verify(h, good, {})
    assert v.failed == 0 and "PASS controller name of station n0001-c (read 'n0001-c')" in v.lines and "PASS controller IP 192.168.1.1 (read 192.168.1.1)" in v.lines
    unnamed = Project(path="", devices=[controller("controller", "192.168.1.9", [("n0002-a", "192.168.1.2")]), device("n0002-a", "192.168.1.2")])
    v = consumer.verify(h, unnamed, {})
    assert "FAIL controller name of station n0001-c (read 'controller')" in v.lines and "FAIL controller IP 192.168.1.1 (read 192.168.1.9)" in v.lines
    assert consumer.controller_is_unnamed("controller") and consumer.controller_is_unnamed("") and not consumer.controller_is_unnamed("n0001-c")


def test_the_exports_controller_name_is_checked(tmp_path):
    body = '<?xml version="1.0"?><ProcessData><Controller displayName="CIFX_RE_PNM[CIFX RE/PNM]&lt;%s&gt;(#1)"><Channel/></Controller></ProcessData>'
    h = handoff_of([])
    for name, kept, expect in (("n0001-c", False, "PASS"), ("controller", False, "FAIL"), ("other-name", True, "PASS")):
        path = str(tmp_path / ("%s.xml" % name))
        open(path, "w", encoding="utf-8").write(body % name)
        v = consumer.Verification()
        consumer.verify_exports(v, h, path, str(tmp_path / "config.nxd"), controller_kept=kept)
        assert lines(v, expect + " process data export: controller"), (name, v.lines)


# ---- the update's NOTEs ---------------------------------------------------------------------------------------- #
def test_an_update_skips_what_the_project_has_and_keeps_what_the_table_lacks():
    h = handoff_of([station("n0002-a", "192.168.1.2"), station("n0003-b", "192.168.1.3")])
    p = Project(path="", devices=[controller("n0001-c", "192.168.1.1", [("n0003-b", "192.168.1.3")]),
                                  device("n0002-a", "192.168.1.99", "SOMETHING ELSE"),     # exists: skipped, however it looks
                                  device("n0003-b", "192.168.1.3"), device("n0009-z", "192.168.1.9")])  # the new one; a kept extra
    v = consumer.verify(h, p, {}, skipped={"n0002-a"}, keep_extras=True)
    assert v.failed == 0, v.report()
    assert "NOTE station n0002-a exists in the project - skipped, not compared (update)" in v.lines
    assert "NOTE node n0009-z in the project is not in the table - kept (update)" in v.lines
    assert "PASS station n0003-b exists" in v.lines and "PASS station n0003-b IP 192.168.1.3 (read 192.168.1.3)" in v.lines
    plain = consumer.verify(h, p, {})
    assert "FAIL station n0002-a IP 192.168.1.2 (read 192.168.1.99)" in plain.lines and lines(plain, "FAIL no station outside the table")


def test_an_update_leaves_a_named_controller_and_fails_an_unnamed_one():
    h = handoff_of([station("n0002-a", "192.168.1.2")])
    kept = Project(path="", devices=[controller("old-name", "192.168.1.7", [("n0002-a", "192.168.1.2")]), device("n0002-a", "192.168.1.2")])
    v = consumer.verify(h, kept, {}, skipped=set(), keep_extras=True)
    assert "NOTE controller name of station 'old-name' kept (table n0001-c) - an update leaves a named controller as it is" in v.lines
    assert "NOTE controller IP 192.168.1.7 kept (table 192.168.1.1) - an update leaves the controller's address" in v.lines
    assert v.failed == 0, v.report()
    unnamed = Project(path="", devices=[controller("controller", "192.168.1.1", [("n0002-a", "192.168.1.2")]), device("n0002-a", "192.168.1.2")])
    v = consumer.verify(h, unnamed, {}, skipped=set(), keep_extras=True)
    assert "FAIL controller name of station n0001-c (read 'controller')" in v.lines, "an update names an unnamed controller - the read-back must show it"


# ---- the canvas of an update ----------------------------------------------------------------------------------- #
def canvas_fixture(tmp_path):
    spec = importlib.util.spec_from_file_location("tc", os.path.join(HERE, "test_canvas.py"))
    tc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tc)
    path = str(tmp_path / "SYCON_net.xml")
    open(path, "w", encoding="utf-8", newline="").write(tc.XML)
    return path


def rects_of(path):
    out = {}
    for el in ET.parse(path).getroot().iter():
        if el.tag.split("}")[-1] == "Device":
            pr = [c for c in el if c.tag.split("}")[-1] == "PositionRect"][0]
            out[el.get("deviceNo")] = tuple(int(pr.get(k)) for k in ("top", "left", "bottom", "right"))
    return out


def bus_bottom(path):
    text = open(path, encoding="utf-8").read()
    m = canvas.VERTICAL_BUS.search(text)
    return int(m.group(0).split('bottom="')[1].split('"')[0]) if m else None


def test_an_update_lays_out_the_new_stations_alone_and_the_bus_reaches_the_lowest(tmp_path):
    path = canvas_fixture(tmp_path)
    before = rects_of(path)
    slaves = [n for n in before if n != "controller"]
    old, new = slaves[0], slaves[1]
    # the user's own layout: the old station far down, the controller moved
    canvas.apply(path, {}, {old: (700, 300, 732, 332)}, controller_rect=(5, 5, 37, 37))
    h = Handoff(folder="", controller={"station_name": "controller"},
                stations=[station(old, "192.168.1.5", symbolic="005_OLD"), station(new, "192.168.1.6", symbolic="006_NEW", fld="=A")])
    n_sym, n_rect = canvas.apply_layout(path, h, only={new})
    assert (n_sym, n_rect) == (1, 1)
    after = rects_of(path)
    assert after[old] == (700, 300, 732, 332) and after["controller"] == (5, 5, 37, 37), "the user's boxes untouched"
    assert after[new] != before[new] and after[new][0] == canvas.FIRST_ROW_TOP, "the new station placed by the rule"
    assert bus_bottom(path) == 732 + canvas.BUS_MARGIN, "the bus reaches the old station far below the new one"
    symbolic = {el.get("deviceNo"): [v for k, v in el.attrib.items() if k.split("}")[-1] == "symbolicName"][0]
                for el in ET.parse(path).getroot().iter() if el.tag.split("}")[-1] == "Device"}
    assert symbolic[new] == "006_NEW" and symbolic[old] != "005_OLD", "the skipped station keeps its label"


# ---- the command and the button -------------------------------------------------------------------------------- #
def test_the_update_command(tmp_path):
    c1 = ws.scan(fake_production(str(tmp_path))).card(1)
    cmd = ws.build_command(c1, update=True)
    assert cmd.label == "update card 1" and cmd.argv[-1] == "--update" and "--resume" not in cmd.argv and cmd.drives_sycon
    assert cmd.log == os.path.join(c1.logs_dir, "build_update.log")
    assert ws.build_command(c1).argv[-1] != "--update"


def test_the_update_button_follows_the_project(tmp_path):
    tk = pytest.importorskip("tkinter")
    from sycon5 import gui
    root = None
    for attempt in range(3):
        try:
            root = tk.Tk()
            break
        except tk.TclError as ex:
            if attempt == 2:
                pytest.skip("no display: %s" % ex)
            time.sleep(0.5)
    root.withdraw()
    try:
        app = gui.App(root, fake_production(str(tmp_path / "PRODUCTION")), settings_path=str(tmp_path / "gui.json"))
        app.tree.selection_set("1")
        root.update()
        assert "disabled" not in app.b_update.state(), "card 1 is built: it can be updated"
        app.tree.selection_set("2")
        root.update()
        assert "disabled" in app.b_update.state(), "card 2 is not built: nothing to update"
    finally:
        root.destroy()
