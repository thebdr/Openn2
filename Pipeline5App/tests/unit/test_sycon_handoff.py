"""The SYCON.net handoff (hw/sycon-*): the build from staged rows and the projection with headers."""
import os
import tempfile

from pipeline5.systems.ipc_based.intervalzero_rtx import sycon_handoff as sycon
from pipeline5.systems.plc_based.siemens_s7 import openn_header as header

DTD = {
    "CIFX80-RE/ML": {"model_id": "CIFX80-RE/ML", "role": "controller", "catalog_item": "CIFX RE/PNM", "modules": "default", "gsdml": "", "comment": ""},
    "6ES7155-6AU01-0BN0": {"model_id": "6ES7155-6AU01-0BN0", "role": "slave", "catalog_item": "IM 155-6 PN ST V4.2", "modules": "iolist", "gsdml": "", "comment": ""},
    "AL1202": {"model_id": "AL1202", "role": "slave", "catalog_item": "AL1202", "modules": "default", "gsdml": "", "comment": ""},
    "6GK5216-4BS00-2AC2": {"model_id": "6GK5216-4BS00-2AC2", "role": "ignore", "catalog_item": "", "modules": "default", "gsdml": "", "comment": "switch"},
}


def _head(name, ip, part, slot, idn, desc="X"):
    return {"profinet_name": name, "profinet_ip": ip, "part_no": part, "slot": slot, "id_node": idn,
            "description_module": desc, "manufacturer": "M", "source_cell": name}


def _signal(slot="", part=""):
    return {"profinet_name": "", "slot": slot, "part_no": part}


ROWS = [
    _head("n0001-trib-aec01-K22101.1", "192.168.1.1", "CIFX 80-RE/ML", "-K22101.1", "1"),
    _head("n0001-trib-aec01-K22201.1", "192.168.1.1", "CIFX 80-RE/ML", "-K22201.1", "1"),
    _head("n0010-trib-aec01-K26501", "192.168.1.10", "6GK5216-4BS00-2AC2", "-K26501", "10"),
    _head("n0005-trib-aep01-K35001", "192.168.1.5", "6ES7155-6AU01-0BN0", "-K35001", "5"),
    _signal("-K35001", "6ES7155-6AU01-0BN0"), _signal("-K35010", "6ES7131-6BH01-0BA0"), _signal("-K35010"),
    {"profinet_name": "", "slot": "-K35030", "part_no": "14C_00058", "manufacturer": "6ES7 132-6BH01-0BA0"},
    _signal("-K35050", ""),
    _head("n0035-trib-sm006-K1", "192.168.1.35", "AL1202", "-K1", "35"),
    _signal("-K1", "AL1202"), _signal("", "O5D100"),
    _head("n0088-trib-ca01-aec1-T3", "192.168.1.88", "", "-T3", "88"),
    _head("n0099-trib-x", "192.168.1.99", "UNKNOWN-1", "-X", "99"),
]


def test_build_stations_modules_findings():
    stations, modules, findings = sycon.build(ROWS, DTD)
    assert [(s["role"], s["station_name"], s["catalog_kind"], s["catalog_item"], s["ip_address"], s["device_number"]) for s in stations] == [
        ("controller", "n0001-trib-aec01-K22101.1", "master", "CIFX RE/PNM", "192.168.1.1", "1"),
        ("slave", "n0005-trib-aep01-K35001", "slave", "IM 155-6 PN ST V4.2", "192.168.1.5", "5"),
        ("slave", "n0035-trib-sm006-K1", "slave", "AL1202", "192.168.1.35", "35"),
    ]
    assert [(m["station_name"], m["slot"], m["module_id"], m["comment"]) for m in modules] == [
        ("n0005-trib-aep01-K35001", "1", "6ES7131-6BH01-0BA0", "-K35010"),
        ("n0005-trib-aep01-K35001", "2", "6ES7132-6BH01-0BA0", "-K35030"),
    ]
    types = sorted(f.type for f in findings)
    assert types == ["sycon_card_without_model", "sycon_head_without_model", "sycon_model_ignored",
                     "sycon_model_not_in_dtd", "sycon_second_controller"]
    assert not any(f.severity == "FAIL" for f in findings)


def test_no_controller_is_a_fail():
    _s, _m, findings = sycon.build(ROWS[3:], DTD)
    assert [f.type for f in findings if f.severity == "FAIL"] == ["sycon_no_controller"]


def test_project_writes_headed_files():
    with tempfile.TemporaryDirectory() as d:
        dtd = os.path.join(d, "SyconDeviceTypesDatabase.csv")
        with open(dtd, "w", encoding="utf-8", newline="") as f:
            f.write("#!openn\r\n#! kind: hw/sycon-device-types\r\n#! schema: 1\r\n#! producer: hand-maintained\r\n"
                    "#! generated: 2026-10-23T13:00:00Z\r\n#!end\r\n# Model Id,Role,Catalog Item,Modules,GSDML,Comment\r\n"
                    "CIFX 80-RE/ML,controller,CIFX RE/PNM,default,,\r\n6ES7155-6AU01-0BN0,slave,IM 155-6 PN ST V4.2,iolist,,\r\n"
                    "AL1202,slave,AL1202,default,,\r\n6GK5216-4BS00-2AC2,ignore,,,,switch\r\n")
        out = os.path.join(d, "SyconNetProjectInterface")
        res = sycon.project(ROWS, out, dtd, source_label="test.xlsx")
        assert res["stations"] == 3 and res["modules"] == 2 and res["controller"] == "n0001-trib-aec01-K22101.1"
        for path, kind in ((res["stations_path"], "hw/sycon-stations"), (res["modules_path"], "hw/sycon-modules"),
                           (res["device_types_db"], "hw/sycon-device-types")):
            text = open(path, encoding="utf-8", newline="").read()
            h = header.read_header(path)
            assert h.get("kind") == kind and h.get("target") == "SyconNetProjectInterface" and str(h.get("schema")) == "1", (path, h)
            assert "\r\n" in text and not text.startswith("﻿")
        stations = open(res["stations_path"], encoding="utf-8").read().splitlines()
        assert stations[-1].startswith("slave,n0035-trib-sm006-K1,slave,AL1202,AL1202,192.168.1.35,255.255.255.0,,35,")
        modules = open(res["modules_path"], encoding="utf-8").read().splitlines()
        assert modules[-1] == "n0005-trib-aep01-K35001,2,6ES7132-6BH01-0BA0,,,-K35030"
        db = open(res["device_types_db"], encoding="utf-8").read()
        assert "CIFX 80-RE/ML,controller" in db and db.count("#!openn") == 1
