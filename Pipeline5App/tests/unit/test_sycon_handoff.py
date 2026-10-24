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
    pg = "potential_group=Enable new potential group (light BaseUnit)"
    assert [(m["station_name"], m["slot"], m["module_id"], m["parameters"], m["comment"]) for m in modules] == [
        ("n0005-trib-aep01-K35001", "1", "6ES7131-6BH01-0BA0", pg, "-K35010"),       # the first module
        ("n0005-trib-aep01-K35001", "2", "6ES7132-6BH01-0BA0", pg, "-K35030"),       # the first output module (DQ)
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


def test_fast_stations_take_2_ms():
    rows = [
        _head("n0001-trib-aec01-K22101.1", "192.168.1.1", "CIFX 80-RE/ML", "-K22101.1", "1"),
        _head("n0035-trib-sm006-K1", "192.168.1.35", "AL1202", "-K1", "35"),
        {"profinet_name": "", "connector": "X01", "pin_no": "4", "bit": "I.35.0.0", "desc_l1": "PHOTOCELL", "desc_l1b": "MISSING BLADE"},
        _head("n0059-trib-sm047-K1", "192.168.1.59", "AL1202", "-K1", "59"),
        {"profinet_name": "", "connector": "X01", "pin_no": "4", "bit": "I.59.0.0", "desc_l1": "PHOTOCELL", "desc_l1b": "CONTROL ZONE =TRIB-CZ01"},
        _head("n0061-trib-sm049-K1", "192.168.1.61", "AL1202", "-K1", "61"),
        {"profinet_name": "", "connector": "X02", "pin_no": "4", "bit": "I.61.0.0", "mnemonic": "LOAD_ACCURACY_01", "desc_l1b": "Load accuracy photocell"},
        _head("n0062-trib-sm050-K1", "192.168.1.62", "AL1202", "-K1", "62"),
        {"profinet_name": "", "connector": "X01", "pin_no": "4", "bit": "I.62.0.0", "desc_l1": "DISTANCE SENSOR", "desc_l1b": "LEFT  SIDE RECENTERING 2"},
    ]
    stations, _m, _f = sycon.build(rows, DTD)
    assert [(s["station_name"], s["update_time_ms"]) for s in stations] == [
        ("n0001-trib-aec01-K22101.1", ""), ("n0035-trib-sm006-K1", "8"), ("n0059-trib-sm047-K1", "2"),
        ("n0061-trib-sm049-K1", "2"), ("n0062-trib-sm050-K1", "2")]
    assert stations[2]["comment"].endswith("fast: control zone") and stations[3]["comment"].endswith("fast: load accuracy")
    assert stations[4]["comment"].endswith("fast: recentering")


def test_potential_group_by_signal_direction():
    """Three DI cards then a DQ then a DI: the first module and the first OUTPUT module get the potential group."""
    rows = [
        _head("n0001-trib-aec01-K22101.1", "192.168.1.1", "CIFX 80-RE/ML", "-K22101.1", "1"),
        _head("n0005-trib-aep01-K35001", "192.168.1.5", "6ES7155-6AU01-0BN0", "-K35001", "5"),
        {"profinet_name": "", "slot": "-K1", "part_no": "6ES7131-6BH01-0BA0", "bit": "I.5.0.0"},
        {"profinet_name": "", "slot": "-K2", "part_no": "6ES7131-6BH01-0BA0", "bit": "I.5.2.0"},
        {"profinet_name": "", "slot": "-K3", "part_no": "UNKNOWN-DQ", "bit": "Q.5.0.0"},
        {"profinet_name": "", "slot": "-K4", "part_no": "UNKNOWN-DQ", "bit": "Q.5.2.0"},
        {"profinet_name": "", "slot": "-K5", "part_no": "6ES7131-6BH01-0BA0", "bit": "I.5.4.0"},
    ]
    _s, modules, _f = sycon.build(rows, DTD)
    assert [(m["slot"], bool(m["parameters"])) for m in modules] == [("1", True), ("2", False), ("3", True), ("4", False), ("5", False)]
    assert sycon.card_is_output([{"bit": "Q.5.0.0"}, {"bit": "I.5.0.0"}], "X") is False      # mixed: not an output module
    assert sycon.card_is_output([{}], "6ES7 132-6BH01-0BA0") is True                        # no addresses: by family


def test_scalance_pnio_row():
    dtd = dict(DTD, **{"6GK5216-4BS00-2AC2": {"model_id": "6GK5216-4BS00-2AC2", "role": "slave", "catalog_item": "SCALANCE XC216-4C V4.4",
                                              "modules": "scalance-pnio", "gsdml": "GSDML-X.xml", "comment": ""}})
    rows = [_head("n0001-trib-aec01-K22101.1", "192.168.1.1", "CIFX 80-RE/ML", "-K22101.1", "1"),
            _head("n0010-trib-aec01-K26501", "192.168.1.10", "6GK5216-4BS00-2AC2", "-K26501", "10")]
    stations, modules, _f = sycon.build(rows, dtd)
    assert [s["station_name"] for s in stations] == ["n0001-trib-aec01-K22101.1", "n0010-trib-aec01-K26501"]
    assert stations[1]["update_time_ms"] == ""          # a switch's updating time is the device's own (128 ms and up)
    assert len(modules) == 5 and modules[0]["slot"] == "0" and modules[0]["subslot"] == "32768" and modules[0]["module_text"] == "PN-IO"
    assert modules[0]["parameters"].startswith("2=Off | 4=Off | record:3=00 03 00 06") and "record:12312=30 1C" in modules[0]["parameters"]
    assert [(m["slot"], m["subslot"], m["module_id"], m["module_text"]) for m in modules[1:]] == [
        ("0", str(32768 + n), "6GK5991-1AD00-8GA0", "SFP 991-1 A") for n in (1, 2, 3, 4)]


def test_duplicate_name_or_ip_is_a_fail_and_the_second_is_left_out():
    rows = [
        _head("n0001-trib-aec01-K22101.1", "192.168.1.1", "CIFX 80-RE/ML", "-K22101.1", "1"),
        _head("n0055-enc04-aec1-k11", "192.168.1.55", "6ES7158-3AD10-0XA0", "-K11", "55"),
        _head("n0055-enc04-aec1-k11", "192.168.1.56", "6ES7158-3AD10-0XA0", "-K11", "56"),     # the name again
        _head("n0057-lb01-K1", "192.168.1.55", "AL1202", "-K1", "57"),                           # the IP again
    ]
    dtd = dict(DTD, **{"6ES7158-3AD10-0XA0": {"model_id": "6ES7158-3AD10-0XA0", "role": "slave", "catalog_item": "PN/PN Coupler X2",
                                               "modules": "default", "gsdml": "", "comment": ""}})
    stations, _m, findings = sycon.build(rows, dtd)
    assert [s["station_name"] for s in stations] == ["n0001-trib-aec01-K22101.1", "n0055-enc04-aec1-k11"]
    assert sorted((f.type, f.severity) for f in findings) == [("sycon_duplicate_ip", "FAIL"), ("sycon_duplicate_name", "FAIL")]


def test_another_network_is_another_project():
    """2026-10-24: the conveyor list's two cabinet sheets are two PROFINET networks with their own cifX cards; the
    second repeats the first's station names. One project = the controller's network: the other network's
    controller and stations are INFO findings, left out (no duplicate FAIL for them); a second card on the
    controller's own network is the redundant one, as before."""
    coupler = {"6ES7158-3AD10-0XA0": {"model_id": "6ES7158-3AD10-0XA0", "role": "slave", "catalog_item": "PN/PN Coupler X2",
                                      "modules": "default", "gsdml": "", "comment": ""}}
    rows = [
        _head("n0001-trib-aec01-K22102.1", "192.168.2.1", "CIFX 80-RE/ML", "-K22102.1", "1"),
        _head("n0001-trib-aec01-K22202.1", "192.168.2.1", "CIFX 80-RE/ML", "-K22202.1", "1"),      # the redundant card
        _head("n0055-enc04-aec1-k11", "192.168.2.55", "6ES7158-3AD10-0XA0", "-K11", "55"),
        _head("n0001-trib-aec01-K22102.2", "192.168.3.1", "CIFX 80-RE/ML", "-K22102.2", "1"),      # the second network
        _head("n0055-enc04-aec1-k11", "192.168.3.55", "6ES7158-3AD10-0XA0", "-K11", "55"),         # its coupler, same name
    ]
    stations, _m, findings = sycon.build(rows, dict(DTD, **coupler))
    assert [(s["station_name"], s["ip_address"]) for s in stations] == [("n0001-trib-aec01-K22102.1", "192.168.2.1"),
                                                                       ("n0055-enc04-aec1-k11", "192.168.2.55")]
    kinds = [(f.type, f.severity) for f in findings]
    assert kinds == [("sycon_second_controller", "INFO"), ("sycon_second_controller", "INFO"), ("sycon_other_network", "INFO")]
    assert "second card on its network" in findings[0].detail and "card 2's controller" in findings[1].detail
    assert "card 2's project" in findings[2].detail
    assert [(c["card"], c["name"], c["net"]) for c in sycon.cards_of(rows, dict(DTD, **coupler))] == [
        (1, "n0001-trib-aec01-K22102.1", (192, 168, 2, 0)), (2, "n0001-trib-aec01-K22102.2", (192, 168, 3, 0))]
    stations2, _m, findings2 = sycon.build(rows, dict(DTD, **coupler), card=2)
    assert [s["station_name"] for s in stations2] == ["n0001-trib-aec01-K22102.2", "n0055-enc04-aec1-k11"]
    assert [f.type for f in findings2] == ["sycon_second_controller", "sycon_second_controller", "sycon_other_network"]
    _s, _m, findings3 = sycon.build(rows, dict(DTD, **coupler), card=3)
    assert [f.type for f in findings3] == ["sycon_no_card"]
    assert sycon.network_of("192.168.3.55") == (192, 168, 3, 0) and sycon.network_of("n/a") is None


def test_two_cards_two_folders():
    """A list with two cifX cards (two networks) gives two card folders, each with its own controller and stations."""
    coupler = {"6ES7158-3AD10-0XA0": {"model_id": "6ES7158-3AD10-0XA0", "role": "slave", "catalog_item": "PN/PN Coupler X2",
                                      "modules": "default", "gsdml": "", "comment": "", "symbolic": "variable", "fixed_modules": []}}
    rows = [
        _head("n0001-trib-aec01-K22102.1", "192.168.2.1", "CIFX 80-RE/ML", "-K22102.1", "1"),
        dict(_head("n0055-enc04-aec1-k11", "192.168.2.55", "6ES7158-3AD10-0XA0", "-K11", "55"), desc_l1b="SORTER (=TRIB) / UPSTREAM"),
        _head("n0001-trib-aec01-K22102.2", "192.168.3.1", "CIFX 80-RE/ML", "-K22102.2", "1"),
        _head("n0055-enc04-aec1-k11", "192.168.3.55", "6ES7158-3AD10-0XA0", "-K11", "55"),
    ]
    with tempfile.TemporaryDirectory() as d:
        dtd = os.path.join(d, "SyconDeviceTypesDatabase.csv")
        with open(dtd, "w", encoding="utf-8", newline="") as f:
            f.write("CIFX 80-RE/ML,controller,CIFX RE/PNM,default,,\r\n"
                    "6ES7158-3AD10-0XA0,slave,PN/PN Coupler X2,default,,,variable\r\n")
        res = sycon.project(rows, os.path.join(d, "PRODUCTION"), dtd)
        assert [(c["card"], c["project"], c["controller"], c["stations"]) for c in res["cards"]] == [
            (1, "HilscherPnCard_1", "n0001-trib-aec01-K22102.1", 2), (2, "HilscherPnCard_2", "n0001-trib-aec01-K22102.2", 2)]
        assert res["stations"] == 4
        for c in res["cards"]:
            assert os.path.isfile(os.path.join(d, "PRODUCTION", "HilscherIOCard%d" % c["card"], "SyconNetProjectInterface", "SyconStations.csv"))
        card1 = open(res["cards"][0]["stations_path"], encoding="utf-8").read().splitlines()
        assert card1[-1].endswith(",SORTER (=TRIB) / UPSTREAM,=TRIB-AEC01-K11") or card1[-1].endswith(",SORTER (=TRIB) / UPSTREAM,"), card1[-1]
        assert "Symbolic Name" in card1[-3] and "FLD" in card1[-3]
        # one project per card: the findings of all cards, each once
        kinds = sorted(f.type for f in res["findings"])
        assert kinds == ["sycon_other_network", "sycon_other_network", "sycon_second_controller", "sycon_second_controller"]
        one = sycon.project(rows, os.path.join(d, "ONE"), dtd, card=2)
        assert [c["card"] for c in one["cards"]] == [2] and one["controller"] == "n0001-trib-aec01-K22102.2"


def test_fixed_modules_symbolic_rules_and_the_manufacturer_key():
    """The Anybus Communicators (user 2026-10-24): the cell test antenna's ABC3013-A plugs IN 0016 + OUT 0012, the
    Vitronic camera head has no Part No. and is keyed by its Manufacturer, plugging IN 0064 + OUT 0064; the
    symbolic names by rule: fld (ET200SP), variable (coupler), description (Anybus), default (the rest)."""
    with tempfile.TemporaryDirectory() as d:
        dtd = os.path.join(d, "SyconDeviceTypesDatabase.csv")
        with open(dtd, "w", encoding="utf-8", newline="") as f:
            f.write("CIFX 80-RE/ML,controller,CIFX RE/PNM,default,,\r\n"
                    "6ES7155-6AU01-0BN0,slave,IM 155-6 PN ST V4.2,iolist,,,fld\r\n"
                    "ABC3013-A,slave,Anybus Communicator,fixed,GSDML-V2.41-HMS.xml,cell test,description,IN 0016 | OUT 0012\r\n"
                    "VITRONIC,slave,Anybus Communicator,fixed,GSDML-V2.41-HMS.xml,camera,description,IN 0064 | OUT 0064\r\n")
        db = sycon.load_dtd(dtd)
        assert db["ABC3013-A"]["fixed_modules"] == ["IN 0016", "OUT 0012"] and db["ABC3013-A"]["symbolic"] == "description"
        assert db["6ES7155-6AU01-0BN0"]["symbolic"] == "fld" and db["CIFX80-RE/ML"]["symbolic"] == "default"
    rows = [
        _head("n0001-trib-aec01-K22101.1", "192.168.1.1", "CIFX 80-RE/ML", "-K22101.1", "1"),
        _head("n0005-trib-aep01-K35001", "192.168.1.5", "6ES7155-6AU01-0BN0", "-K35001", "5"),
        _head("n0002-trib-ct01-aec1-A1", "192.168.1.2", "ABC3013-A", "-A1", "2", desc="ANTENNA CELL TEST"),
        {"profinet_name": "n0088-trib-ca01-aec1-T3", "profinet_ip": "192.168.1.88", "part_no": "", "manufacturer": "VITRONIC",
         "description_module": "PROFINET CONTROLLER", "slot": "-T3", "id_node": "88", "functional_unit": "=TRIB",
         "location": "-CA01-AEC1", "device": "-T3", "combined_FLD": "=TRIB-CA01-AEC1-T3"},
        {"profinet_name": "n0099-x", "profinet_ip": "192.168.1.99", "part_no": "", "manufacturer": "NOBODY", "slot": "-X"},
    ]
    for r in rows[:3]:
        r.update({"functional_unit": "=TRIB", "location": "-AEP01" if "aep01" in r["profinet_name"] else "-AEC01"})
    stations, modules, findings = sycon.build(rows, db)
    assert [(s["station_name"], s["symbolic_name"]) for s in stations] == [
        ("n0001-trib-aec01-K22101.1", ""), ("n0005-trib-aep01-K35001", "=TRIB-AEP01"),
        ("n0002-trib-ct01-aec1-A1", "ANTENNA CELL TEST"), ("n0088-trib-ca01-aec1-T3", "PROFINET CONTROLLER")]
    assert stations[3]["fld"] == "=TRIB-CA01-AEC1-T3" and stations[3]["model_id"] == "VITRONIC"
    assert [(m["station_name"], m["slot"], m["module_text"]) for m in modules] == [
        ("n0002-trib-ct01-aec1-A1", "1", "IN 0016"), ("n0002-trib-ct01-aec1-A1", "2", "OUT 0012"),
        ("n0088-trib-ca01-aec1-T3", "1", "IN 0064"), ("n0088-trib-ca01-aec1-T3", "2", "OUT 0064")]
    assert [(f.type, f.severity) for f in findings] == [("sycon_model_by_manufacturer", "INFO"), ("sycon_head_without_model", "WARN")]
    try:
        sycon.load_dtd.__wrapped__  # noqa: B018 - no wrapper: the refusals below go through the loader itself
    except AttributeError:
        pass
    with tempfile.TemporaryDirectory() as d:
        bad = os.path.join(d, "SyconDeviceTypesDatabase.csv")
        with open(bad, "w", encoding="utf-8", newline="") as f:
            f.write("ABC3013-A,slave,Anybus Communicator,fixed,,,description,\r\n")
        try:
            sycon.load_dtd(bad)
        except ValueError as ex:
            assert "policy fixed without Fixed Modules" in str(ex)
        else:
            raise AssertionError("a fixed policy without modules was accepted")
        with open(bad, "w", encoding="utf-8", newline="") as f:
            f.write("ABC3013-A,slave,Anybus Communicator,default,,,label\r\n")
        try:
            sycon.load_dtd(bad)
        except ValueError as ex:
            assert "symbolic-name rule" in str(ex)
        else:
            raise AssertionError("an unknown symbolic-name rule was accepted")


def test_coupler_modules_mirrored_by_connector():
    """User 2026-10-24: a PN/PN coupler plugs *OUT 128 Byte + *IN 128 Byte on its X2 side and the mirror on X1; the
    head row's Connector column picks the list; a connector without a list is a WARN, nothing plugged."""
    assert sycon.fixed_modules("X2: *OUT 128 Byte | *IN 128 Byte; X1: *IN 128 Byte | *OUT 128 Byte") == {
        "X2": ["*OUT 128 Byte", "*IN 128 Byte"], "X1": ["*IN 128 Byte", "*OUT 128 Byte"]}
    assert sycon.fixed_modules("IN 0016 | OUT 0012") == ["IN 0016", "OUT 0012"] and sycon.fixed_modules("") == []
    dtd = dict(DTD, **{"6ES7158-3AD10-0XA0": {"model_id": "6ES7158-3AD10-0XA0", "role": "slave", "catalog_item": "PN/PN Coupler X2",
                                               "modules": "fixed", "gsdml": "", "comment": "", "symbolic": "variable",
                                               "fixed_modules": sycon.fixed_modules("X2: *OUT 128 Byte | *IN 128 Byte; X1: *IN 128 Byte | *OUT 128 Byte")}})
    rows = [
        _head("n0001-trib-aec01-K22101.1", "192.168.1.1", "CIFX 80-RE/ML", "-K22101.1", "1"),
        dict(_head("n0006-trib-aec01-K24501", "192.168.1.6", "6ES7158-3AD10-0XA0", "-K24501", "6"), connector="X2"),
        dict(_head("n0007-trib-aec01-K24502", "192.168.1.7", "6ES7158-3AD10-0XA0", "-K24502", "7"), connector="x1"),
        dict(_head("n0008-trib-aec01-K24503", "192.168.1.8", "6ES7158-3AD10-0XA0", "-K24503", "8"), connector=""),
    ]
    stations, modules, findings = sycon.build(rows, dtd)
    assert [(m["station_name"], m["slot"], m["module_text"]) for m in modules] == [
        ("n0006-trib-aec01-K24501", "1", "*OUT 128 Byte"), ("n0006-trib-aec01-K24501", "2", "*IN 128 Byte"),
        ("n0007-trib-aec01-K24502", "1", "*IN 128 Byte"), ("n0007-trib-aec01-K24502", "2", "*OUT 128 Byte")]
    assert [(f.type, f.severity) for f in findings] == [("sycon_connector_unknown", "WARN")]
    assert "n0008-trib-aec01-K24503" in findings[0].detail and len(stations) == 4


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
        out = os.path.join(d, "PRODUCTION")
        res = sycon.project(ROWS, out, dtd, source_label="test.xlsx")
        assert res["stations"] == 3 and res["modules"] == 2 and res["controller"] == "n0001-trib-aec01-K22101.1"
        assert [c["card"] for c in res["cards"]] == [1] and res["cards"][0]["project"] == "HilscherPnCard_1"
        assert res["cards"][0]["dir"] == os.path.join(out, "HilscherIOCard1", "SyconNetProjectInterface")
        for path, kind in ((res["stations_path"], "hw/sycon-stations"), (res["modules_path"], "hw/sycon-modules"),
                           (res["device_types_db"], "hw/sycon-device-types")):
            text = open(path, encoding="utf-8", newline="").read()
            h = header.read_header(path)
            assert h.get("kind") == kind and h.get("target") == "SyconNetProjectInterface" and str(h.get("schema")) == "1", (path, h)
            assert "\r\n" in text and not text.startswith("﻿")
        stations = open(res["stations_path"], encoding="utf-8").read().splitlines()
        assert stations[-1].startswith("slave,n0035-trib-sm006-K1,slave,AL1202,AL1202,,192.168.1.35,255.255.255.0,,8,35,")
        assert stations[-3].startswith("controller,n0001-trib-aec01-K22101.1,master,CIFX RE/PNM,CIFX80-RE/ML,,192.168.1.1,255.255.255.0,,,1,")
        assert stations[-2].startswith("slave,n0005-trib-aep01-K35001,slave,IM 155-6 PN ST V4.2,6ES7155-6AU01-0BN0,"
                                       "GSDML-V2.43-Siemens-ET200SP-20240425.xml,192.168.1.5,")
        modules = open(res["modules_path"], encoding="utf-8").read().splitlines()
        assert modules[-1] == "n0005-trib-aep01-K35001,2,,6ES7132-6BH01-0BA0,,potential_group=Enable new potential group (light BaseUnit),-K35030"
        db = open(res["device_types_db"], encoding="utf-8").read()
        assert "CIFX 80-RE/ML,controller" in db and db.count("#!openn") == 1
