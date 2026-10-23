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


def _port(conn, pin, bit, device=""):
    return {"profinet_name": "", "connector": conn, "pin_no": pin, "bit": bit, "device": device}


PORT_ROWS = [
    _head("n0001-trib-aec01-K22101.1", "192.168.1.1", "CIFX 80-RE/ML", "-K22101.1", "1"),
    _head("n0035-trib-sm006-K1", "192.168.1.35", "AL1202", "-K1", "35"),
    _port("X01", "4", "I.35.0.0", "-B1R"), _port("X01", "2", "I.35.0.1", "-B2R"), _port("X01", "", "I.35.0.7"),
    _port("X02", "4", ""), _port("X02", "2", ""),
    _port("X03", "4", "", "-K3"),                                     # a digital output: its Q row comes below
    _port("X04", "4", "I.35.2.0", "-B4"), _port("X04", "", "I.35.4.7"),   # an IO-Link In 2 Byte device
    _port("X05", "4", "I.35.5.0", "-MO1"), _port("X05", "", "I.35.37.7"),
    _port("X06", "4", "I.35.38.0", "-MO2"), _port("X06", "", "I.35.70.7"),
    _port("X07", "4", "", "-H"), _port("X07", "", "I.35.71.7"),
    _port("X08", "4", ""), _port("X08", "2", ""),
    _port("X03", "4", "Q.35.0.0", "-K3"),
    _port("X05", "4", "Q.35.1.0", "-MO1"),
    _port("X06", "4", "Q.35.33.0", "-MO2"),
    _port("X07", "4", "", "-H"), _port("", "", "Q.35.65.0", "H1"), _port("", "", "Q.35.66.0", "P4"),
    _port("", "", "Q.35.66.6", "P1"),
    _head("n0036-trib-sm007-K1", "192.168.1.36", "AL1202", "-K1", "36"),
    _port("X01", "4", "I.36.0.0", "-B1"), _port("X01", "", "I.36.4.7"),   # 5 input bytes: no such port device
]
PORT_DTD = dict(DTD, AL1202={"model_id": "AL1202", "role": "slave", "catalog_item": "AL1202", "modules": "iolink-ports",
                             "gsdml": "GSDML-V2.34-ifm-AL1202-20181105.xml", "comment": ""})


def test_iolink_ports_from_the_connector_rows():
    stations, modules, findings = sycon.build(PORT_ROWS, PORT_DTD)
    assert [s["station_name"] for s in stations] == ["n0001-trib-aec01-K22101.1", "n0035-trib-sm006-K1", "n0036-trib-sm007-K1"]
    first = [(m["slot"], m["subslot"], m["module_text"], m["comment"]) for m in modules if m["station_name"] == "n0035-trib-sm006-K1"]
    assert first == [
        ("1", "2", "Digital Input + PQI", "X01 [1 in, 0 out] -B1R -B2R"),
        ("1", "3", "Disabled", "X02 [0 in, 0 out] "),
        ("1", "4", "Digital Output + PQI", "X03 [0 in, 1 out] -K3"),
        ("1", "5", "IO-Link In 2 Byte + PQI", "X04 [3 in, 0 out] -B4"),
        ("1", "6", "IO-Link In/Out 32/32 Byte + PQI", "X05 [33 in, 1 out] -MO1"),
        ("1", "7", "IO-Link In/Out 32/32 Byte + PQI", "X06 [33 in, 1 out] -MO2"),
        ("1", "8", "IO-Link Out  2 Byte + PQI", "X07 [1 in, 2 out] -H H1 P1 P4"),
        ("1", "9", "Disabled", "X08 [0 in, 0 out] "),
    ]
    assert all(m["module_id"] == "" for m in modules)
    second = [(m["subslot"], m["module_text"]) for m in modules if m["station_name"] == "n0036-trib-sm007-K1"]
    assert len(second) == 7 and ("2", "Digital Input + PQI") not in second
    warn = [f for f in findings if f.type == "sycon_port_footprint_unknown"]
    assert len(warn) == 1 and "n0036-trib-sm007-K1" in warn[0].detail and "X01" in warn[0].detail


def test_unknown_modules_policy_is_refused():
    with tempfile.TemporaryDirectory() as d:
        dtd = os.path.join(d, "SyconDeviceTypesDatabase.csv")
        with open(dtd, "w", encoding="utf-8", newline="") as f:
            f.write("AL1202,slave,AL1202,ports,,\r\n")
        try:
            sycon.load_dtd(dtd)
        except ValueError as ex:
            assert "modules policy" in str(ex)
        else:
            raise AssertionError("an unknown modules policy was accepted")


def test_no_controller_is_a_fail():
    _s, _m, findings = sycon.build(ROWS[3:], DTD)
    assert [f.type for f in findings if f.severity == "FAIL"] == ["sycon_no_controller"]


def test_project_writes_headed_files():
    with tempfile.TemporaryDirectory() as d:
        dtd = os.path.join(d, "SyconDeviceTypesDatabase.csv")
        with open(dtd, "w", encoding="utf-8", newline="") as f:
            f.write("#!openn\r\n#! kind: hw/sycon-device-types\r\n#! schema: 1\r\n#! producer: hand-maintained\r\n"
                    "#! generated: 2026-10-23T13:00:00Z\r\n#!end\r\n# Model Id,Role,Catalog Item,Modules,GSDML,Comment\r\n"
                    "CIFX 80-RE/ML,controller,CIFX RE/PNM,default,,\r\n"
                    "6ES7155-6AU01-0BN0,slave,IM 155-6 PN ST V4.2,iolist,GSDML-V2.43-Siemens-ET200SP-20240425.xml,\r\n"
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
        assert stations[-1].startswith("slave,n0035-trib-sm006-K1,slave,AL1202,AL1202,,192.168.1.35,255.255.255.0,,35,")
        assert stations[-2].startswith("slave,n0005-trib-aep01-K35001,slave,IM 155-6 PN ST V4.2,6ES7155-6AU01-0BN0,"
                                       "GSDML-V2.43-Siemens-ET200SP-20240425.xml,192.168.1.5,")
        modules = open(res["modules_path"], encoding="utf-8").read().splitlines()
        assert modules[-1] == "n0005-trib-aep01-K35001,2,,6ES7132-6BH01-0BA0,,,-K35030"
        db = open(res["device_types_db"], encoding="utf-8").read()
        assert "CIFX 80-RE/ML,controller" in db and db.count("#!openn") == 1
