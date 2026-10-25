"""C-047 refute round 1 (2026-10-26): the handoff reader and loader attacked with Excel's habits and bad tables, the
verification with projects that lie, the canvas with hostile labels. What broke and was fixed: a `;` table whose
first row quotes a field full of commas split on the commas (the delimiter is now counted outside quotes); a header
without `#!end` read as a table with no rows; module rows of a station not in the stations table were kept and
never applied or verified; a station name twice (SYCON.net's names are case-insensitive) or an IP twice were
accepted into a build; a project with the same station twice verified clean; a project without a controller crashed
the verification instead of failing it. What held: two controllers refused, Excel's trailing delimiters tolerated,
a missing station / a wrong IP / a short record fail, a longer record passes by prefix (documented), the order-number
patterns, the canvas escaping, idempotence and re-apply, the 8-per-row wrap."""
import importlib.util
import os
import sys

import pytest
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)
from sycon5 import canvas, consumer, handoff  # noqa: E402
from sycon5.readback import Device, Project  # noqa: E402

HEADER = "#!openn\n#! kind: %s\n#! schema: 1\n#!end\n"
STATIONS_COLUMNS = "# Role,Station Name,Catalog Kind,Catalog Item,Model Id,GSDML,IP Address,Subnet Mask,Gateway,Update Time,Comment\n"
MODULES_COLUMNS = "# Station Name,Slot,Module Id,Module Text,Parameters,Comment\n"


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    return path


def tables(tmp_path, stations_rows, modules_rows=""):
    folder = str(tmp_path / "SyconNetProjectInterface")
    write(os.path.join(folder, "SyconStations.csv"), HEADER % "hw/sycon-stations" + STATIONS_COLUMNS + stations_rows)
    if modules_rows is not None:
        write(os.path.join(folder, "SyconModules.csv"), HEADER % "hw/sycon-modules" + MODULES_COLUMNS + modules_rows)
    return folder


CONTROLLER = "controller,n0001-c,master,CIFX RE/PNM,CIFX80-RE/ML,,192.168.1.1,255.255.255.0,,,\n"


# ---- the reader ------------------------------------------------------------------------------------------------ #
def test_a_quoted_field_full_of_the_other_delimiter(tmp_path):
    p = write(str(tmp_path / "semi.csv"), HEADER % "x" + "# A;B;C\n" + 'a;"x,y,z";c\n')
    assert handoff.read_headed_csv(p)[1] == [["a", "x,y,z", "c"]]
    p = write(str(tmp_path / "comma.csv"), HEADER % "x" + "# A,B,C\n" + 'a,"x;y;z",c\n')
    assert handoff.read_headed_csv(p)[1] == [["a", "x;y;z", "c"]]


def test_a_header_never_closed_is_refused(tmp_path):
    p = write(str(tmp_path / "open.csv"), "#!openn\n#! kind: hw/sycon-stations\n# Role,Station Name\ncontroller,n1\n")
    with pytest.raises(handoff.HandoffError, match="never closed"):
        handoff.read_headed_csv(p)


def test_excels_trailing_delimiters_are_tolerated(tmp_path):
    folder = tables(tmp_path, "", None)
    write(os.path.join(folder, "SyconStations.csv"),
          "#!openn,,,\n#! kind: hw/sycon-stations,,,\n#! schema: 1,,,\n#!end,,,\n" + STATIONS_COLUMNS.rstrip("\n") + ",,,\n"
          + CONTROLLER.rstrip("\n") + ",,,\n" + "slave,n0002-a,slave,AL1202,AL1202,,192.168.1.2,255.255.255.0,,,,,,,\n")
    h = handoff.load_handoff(folder)
    assert h.headers["stations"]["kind"] == "hw/sycon-stations" and [s["station_name"] for s in h.stations] == ["n0002-a"]
    assert h.stations[0]["ip_address"] == "192.168.1.2" and h.stations[0]["comment"] == ""


# ---- the loader ------------------------------------------------------------------------------------------------ #
def test_module_rows_of_an_unknown_station_are_refused(tmp_path):
    folder = tables(tmp_path, CONTROLLER + "slave,n0002-a,slave,AL1202,AL1202,,192.168.1.2,255.255.255.0,,,\n",
                    "n0002-a,1,M1,Mod,,\nn0009-x,1,M1,Mod,,\n")
    with pytest.raises(handoff.HandoffError, match=r"not in SyconStations.csv: \['n0009-x'\]"):
        handoff.load_handoff(folder)


def test_a_station_name_twice_in_any_case_is_refused(tmp_path):
    folder = tables(tmp_path, CONTROLLER + "slave,n0002-a,slave,AL1202,AL1202,,192.168.1.2,255.255.255.0,,,\n"
                    "slave,N0002-A,slave,AL1202,AL1202,,192.168.1.3,255.255.255.0,,,\n")
    with pytest.raises(handoff.HandoffError, match="station name 'n0002-a' twice"):
        handoff.load_handoff(folder)


def test_an_ip_twice_is_refused_but_two_empty_ips_are_not(tmp_path):
    folder = tables(tmp_path, CONTROLLER + "slave,n0002-a,slave,AL1202,AL1202,,192.168.1.2,255.255.255.0,,,\n"
                    "slave,n0003-b,slave,AL1202,AL1202,,192.168.1.2,255.255.255.0,,,\n")
    with pytest.raises(handoff.HandoffError, match="IP address 192.168.1.2 twice"):
        handoff.load_handoff(folder)
    folder = tables(tmp_path / "b", CONTROLLER + "slave,n0002-a,slave,AL1202,AL1202,,,,,,\nslave,n0003-b,slave,AL1202,AL1202,,,,,,\n")
    assert len(handoff.load_handoff(folder).stations) == 2


def test_two_controllers_are_refused(tmp_path):
    folder = tables(tmp_path, CONTROLLER + CONTROLLER.replace("n0001-c", "n0001-d").replace("192.168.1.1", "192.168.1.9"))
    with pytest.raises(handoff.HandoffError, match="2 controller rows"):
        handoff.load_handoff(folder)


# ---- the verification ------------------------------------------------------------------------------------------ #
def station(name, ip, catalog_item="AL1202", model_id="AL1202"):
    return {"role": "slave", "station_name": name, "catalog_kind": "slave", "catalog_item": catalog_item, "model_id": model_id,
            "gsdml": "", "ip_address": ip, "subnet_mask": "255.255.255.0", "gateway": "", "update_time_ms": "", "comment": "",
            "symbolic_name": "", "fld": ""}


def device(name, ip, type_name="AL1202"):
    return Device(device_no=name, symbolic="", prog_id="x.PNIOSlave", gsdml="", name=name, ip=ip, type_name=type_name,
                  manufacturer_id=1, device_type_id=2)


def controller(network):
    return Device(device_no="n0001-c", symbolic="", prog_id="x.PNIOController", gsdml="", name="n0001-c", network=list(network))


def handoff_of(stations, modules=None):
    return handoff.Handoff(folder="", controller={"station_name": "n0001-c"}, stations=stations, modules=modules or {})


def fails(v):
    return [ln for ln in v.lines if ln.startswith("FAIL ")]


def test_a_clean_project_verifies_clean():
    h = handoff_of([station("n0002-a", "192.168.1.2")])
    p = Project(path="", devices=[controller([("n0002-a", "192.168.1.2")]), device("n0002-a", "192.168.1.2")])
    v = consumer.verify(h, p, {})
    assert v.failed == 0 and v.ok >= 6, v.report()


def test_a_missing_station_a_wrong_ip_and_an_extra_device_fail():
    h = handoff_of([station("n0002-a", "192.168.1.2"), station("n0003-b", "192.168.1.3")])
    p = Project(path="", devices=[controller([("n0002-a", "192.168.1.2")]), device("n0002-a", "192.168.1.22"), device("n0007-z", "192.168.1.7")])
    v = consumer.verify(h, p, {})
    assert "FAIL station n0003-b exists" in fails(v)
    assert "FAIL station n0002-a IP 192.168.1.2 (read 192.168.1.22)" in fails(v)
    assert any(ln.startswith("FAIL no station outside the table (extra: ['n0007-z'])") for ln in fails(v)), v.report()


def test_the_same_station_twice_in_the_project_fails():
    h = handoff_of([station("n0002-a", "192.168.1.2")])
    p = Project(path="", devices=[controller([("n0002-a", "192.168.1.2")]), device("n0002-a", "192.168.1.2"), device("N0002-A", "192.168.1.2")])
    v = consumer.verify(h, p, {})
    assert "FAIL no station name twice in the project (twice: ['n0002-a'])" in fails(v), v.report()


def test_a_project_without_a_controller_fails_instead_of_crashing():
    h = handoff_of([station("n0002-a", "192.168.1.2")])
    p = Project(path="", devices=[device("n0002-a", "192.168.1.2")])
    assert p.controller is None
    v = consumer.verify(h, p, {})
    assert "FAIL controller present: None" in fails(v) and "FAIL controller lists n0002-a at 192.168.1.2 (read None)" in fails(v), v.report()


def test_a_record_shorter_than_the_table_fails_and_a_longer_one_passes_by_prefix():
    rows = {"n0002-a": [{"station_name": "n0002-a", "slot": "0", "subslot": "1", "module_id": "", "module_text": "", "parameters": "record:1=00 0C 00 02", "comment": ""}]}
    h = handoff_of([station("n0002-a", "192.168.1.2")], rows)
    d = device("n0002-a", "192.168.1.2")
    d.records[(0, 1, 1)] = bytes.fromhex("000c")
    v = consumer.verify(h, Project(path="", devices=[controller([("n0002-a", "192.168.1.2")]), d]), {})
    assert "FAIL station n0002-a slot 0 sub 1 record 1: 00 0c (table 00 0c 00 02)" in fails(v), v.report()
    d.records[(0, 1, 1)] = bytes.fromhex("000c0002ffff")
    v = consumer.verify(h, Project(path="", devices=[controller([("n0002-a", "192.168.1.2")]), d]), {})
    assert v.failed == 0, v.report()


def test_order_number_patterns():
    assert consumer.order_is_pattern("13xx.xx7x.xxxx.x") and consumer.order_is_pattern("T_ID_DAP_DESCRIPTION")
    assert not consumer.order_is_pattern("6ES7158-3AD10-0XA0") and not consumer.order_is_pattern("AL1202") and not consumer.order_is_pattern("")


# ---- the canvas ------------------------------------------------------------------------------------------------ #
def canvas_fixture(tmp_path):
    spec = importlib.util.spec_from_file_location("tc", os.path.join(HERE, "test_canvas.py"))
    tc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tc)
    path = write(str(tmp_path / "SYCON_net.xml"), tc.XML)
    root = ET.parse(path).getroot()
    slaves = [el.get("deviceNo") for el in root.iter() if el.tag.split("}")[-1] == "Device" and el.get("deviceNo") != "controller"]
    return path, slaves


def symbolic_of(path, device_no):
    for el in ET.parse(path).getroot().iter():
        if el.tag.split("}")[-1] == "Device" and el.get("deviceNo") == device_no:
            return [v for k, v in el.attrib.items() if k.split("}")[-1] == "symbolicName"][0]


def test_hostile_labels_round_trip_and_the_apply_is_idempotent(tmp_path):
    path, slaves = canvas_fixture(tmp_path)
    label = 'A & "B" <c> > d'
    assert canvas.apply(path, {slaves[0]: label}, {slaves[0]: (100, 60, 132, 92)}) == (1, 2)
    assert symbolic_of(path, slaves[0]) == label
    before = open(path, "rb").read()
    assert canvas.apply(path, {slaves[0]: label}, {slaves[0]: (100, 60, 132, 92)}) == (0, 2)
    assert open(path, "rb").read() == before, "the same layout again changes nothing"
    assert canvas.apply(path, {slaves[0]: "plain"}, {slaves[0]: (100, 60, 132, 92)}) == (1, 2)
    assert symbolic_of(path, slaves[0]) == "plain"
    assert canvas.apply(path, {"nobody": "x"}, {"nobody": (1, 2, 3, 4)}) == (0, 1), "an unknown station writes nothing but the controller's box"


def test_more_than_eight_stations_wrap_to_the_next_row():
    stations = [{"station_name": "n%03d" % i, "catalog_item": "AL1202", "fld": ""} for i in range(20)]
    rects = canvas.layout(stations)
    tops = sorted(r[0] for r in rects.values())
    assert tops[:8] == [canvas.FIRST_ROW_TOP + i * canvas.DY for i in range(8)]
    assert tops[8] == canvas.FIRST_ROW_TOP + canvas.ROW_PITCH and tops[16] == canvas.FIRST_ROW_TOP + 2 * canvas.ROW_PITCH
    assert len(rects) == 20 and len({r[1] for r in rects.values()}) == 8
