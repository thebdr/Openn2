"""M7 gate (data-independent): Phase 700 Hardware Generation.

The helpers (role, address parse, param merge/override, I/O-address template), the single-pass
extract (stations + modules incl. auto-plugged skip, PotentialGroup, by-type channel params,
default cards), the missing-DTD ERROR/WARNING, the format-2 output (no BOM, CRLF, descriptive
headers), and the phase wiring.
"""
import os
import tempfile
from _harness import run, eq, ok

from pipeline3.core import config
from pipeline3.context import PipelineContext
from pipeline3.domain import hardware
import pipeline3.phases  # registers all phases
from pipeline3.phases import p700_hardware
from pipeline3.registry import registry


def _dtd_rec(model, dev_type="IoDeviceCard", comment="", params_by_type=None, io_addr="", parent=None):
    return {"model_id": model, "dev_type": dev_type, "order": "", "comment": comment, "params": "",
            "params_by_type": params_by_type or {}, "io_addr_params": io_addr, "parent": parent}


def _dtd():
    by_id = {
        "CPU1": _dtd_rec("CPU1", "Plc", "CPU 1518"),
        "COUPLER": _dtd_rec("COUPLER", "IoDevice", "PN/PN Coupler", io_addr="%I%+0"),
        "DI16": _dtd_rec("DI16", "IoDeviceCard", "DI 16x24VDC", params_by_type={"A": "Ch(#).Filter=1"}),
        "DQ16": _dtd_rec("DQ16", "IoDeviceCard", "DQ 16x24VDC"),
        "COUPLER:PS": _dtd_rec("COUPLER:PS", "IoDeviceCard", "Power Supply", parent="COUPLER"),
    }
    return {"by_id": {k.upper(): v for k, v in by_id.items()},
            "default_cards": {"COUPLER": ["COUPLER:PS"]}}


def _rows():
    return [
        {"script_type": "PLC", "part_no": "CPU1", "profinet_name": "n1", "profinet_ip": "192.168.50.1",
         "functional_unit": "=S1", "slot": "-K1", "type_hw": "", "bit": "", "_source_sheet": "NS50", "_source_row": 2},
        {"script_type": "", "type_hw": "PA", "part_no": "COUPLER", "profinet_name": "n6",
         "profinet_ip": "192.168.50.6", "functional_unit": "=S1", "slot": "-K6", "bit": "",
         "_source_sheet": "NS50", "_source_row": 3},
        {"script_type": "A", "part_no": "DI16", "slot": "-C1", "bit": "I0.0", "_source_sheet": "NS50", "_source_row": 4},
        {"script_type": "A", "part_no": "DI16", "slot": "-C1", "bit": "I0.1", "_source_sheet": "NS50", "_source_row": 5},
        {"script_type": "A", "part_no": "DQ16", "slot": "-C2", "bit": "Q0.0", "_source_sheet": "NS50", "_source_row": 6},
        {"script_type": "A", "part_no": "DI16", "slot": "-K6", "bit": "I8.0", "_source_sheet": "NS50", "_source_row": 7},  # auto-plug (head tag)
    ]


# --- helpers ------------------------------------------------------------------------------- #

def test_role():
    eq(hardware._role({"script_type": "PLC"}), "Plc")
    eq(hardware._role({"script_type": "PlcCardCm"}), "PlcCardCm")
    eq(hardware._role({"type_hw": "PA"}), "IoDevice")
    eq(hardware._role({"type_hw": "A"}), None)
    eq(hardware._role({"script_type": "A", "type_hw": ""}), None)


def test_parse_address():
    eq(hardware.parse_address("I20.3"), ("I", 20, 3))
    eq(hardware.parse_address("Q0.0"), ("Q", 0, 0))
    eq(hardware.parse_address(""), None); eq(hardware.parse_address("PA"), None)


def test_merge_params_override():
    eq(hardware._merge_params("a=1|b=2", "b=3|c=4"), "a=1 | b=3 | c=4", "later blob overrides by key")
    eq(hardware._merge_params("PotentialGroup=1", "", "x=9"), "PotentialGroup=1 | x=9")
    eq(hardware._merge_params("flag", "flag"), "flag", "valueless token kept once")


def test_resolve_addr_template():
    eq(hardware._resolve_addr_template("%I%", 10, None), "10")
    eq(hardware._resolve_addr_template("%I% + 2", 10, None), "12")
    eq(hardware._resolve_addr_template("%Q%", None, 20), "20")
    eq(hardware._resolve_addr_template("%I%", None, None), "%I%", "no base -> left as-is")


# --- extract ------------------------------------------------------------------------------- #

def test_extract_stations_and_modules():
    stations, modules, messages = hardware.extract(_rows(), _dtd())
    eq(messages, [], "all models in the DTD")
    eq([s["Role"] for s in stations], ["Plc", "IoDevice"])
    plc = stations[0]
    eq(plc["Station Name"], "n1"); eq(plc["Model Id"], "CPU1"); eq(plc["Subnet"], "Subnet50")
    eq(plc["Group"], "=S1_IODevices")
    # modules for the IoDevice n6: cards -C1, -C2 (the -K6 head-tag card is auto-plugged), + default PS card
    names = [(m["Slot"], m["Module Name"], m["Model Id"]) for m in modules]
    eq(names, [(1, "-C1", "DI16"), (2, "-C2", "DQ16"), (3, "COUPLER:PS", "COUPLER:PS")])
    c1 = modules[0]
    eq(c1["Station Name"], "n6"); eq(c1["I Addr"], 0); eq(c1["Q Addr"], 0); eq(c1["Comment"], "DI 16x24VDC")
    eq(c1["Custom Parameters"], "PotentialGroup=1 | Ch(0).Filter=1 | Ch(1).Filter=1",
       "first card PotentialGroup + per-channel by-type params")
    eq(modules[1]["Custom Parameters"], "", "2nd card: no PotentialGroup, no by-type")
    eq(modules[2]["Custom Parameters"], "", "default card carries no params (DTD col-5 -> Open2App)")


def test_extract_auto_plug_skipped():
    stations, modules, _ = hardware.extract(_rows(), _dtd())
    ok(all(m["Module Name"] != "-K6" for m in modules), "the card whose slot == the device tag is auto-plugged")


def test_station_io_addr_and_ag_override():
    rows = [
        {"script_type": "", "type_hw": "PA", "part_no": "COUPLER", "profinet_name": "n9",
         "profinet_ip": "192.168.51.9", "functional_unit": "=S2", "slot": "-K9",
         "hardware_params": "Foo=override", "bit": "", "_source_sheet": "NS", "_source_row": 2},
        {"script_type": "A", "part_no": "DI16", "slot": "-C1", "bit": "I40.0", "_source_sheet": "NS", "_source_row": 3},
    ]
    dtd = _dtd()
    dtd["by_id"]["COUPLER"]["io_addr_params"] = "Addr.Start=%I%"
    stations, _m, _ = hardware.extract(rows, dtd)
    eq(stations[0]["Subnet"], "Subnet51")
    eq(stations[0]["Custom Parameters"], "Addr.Start=40 | Foo=override",
       "%I% -> device start byte (40), then col-AG appended last")


def test_missing_dtd_error_and_switch_warning():
    rows = [
        {"script_type": "PLC", "part_no": "UNKNOWN_CPU", "profinet_name": "n1",
         "_source_sheet": "NS", "_source_row": 2, "device": "-K1"},
        {"script_type": "PLC", "part_no": "SW1", "description_module": "MANAGED SWITCH",
         "profinet_name": "n2", "_source_sheet": "NS", "_source_row": 3, "device": "-K2"},
    ]
    stations, _m, messages = hardware.extract(rows, _dtd())
    eq(stations, [], "neither head is generatable")
    levels = sorted(level for level, _ in messages)
    eq(levels, ["ERROR", "WARNING"])
    ok(any("UNKNOWN_CPU" in t and lvl == "ERROR" for lvl, t in messages))
    ok(any("switch" in t.lower() and lvl == "WARNING" for lvl, t in messages))


# --- format-2 output ----------------------------------------------------------------------- #

def test_format2_output():
    with tempfile.TemporaryDirectory() as d:
        stations, modules, _ = hardware.extract(_rows(), _dtd())
        spath = hardware.write_stations(stations, d)
        mpath = hardware.write_modules(modules, d)
        sraw = open(spath, "rb").read()
        ok(not sraw.startswith(b"\xef\xbb\xbf"), "no BOM (matches the reference)")
        ok(sraw.count(b"\n") > 0 and sraw.count(b"\n") == sraw.count(b"\r\n"), "CRLF only")
        s = sraw.decode("utf-8")
        ok(s.startswith("#!format=2,,,,,,,,\r\n"), "Stations format-2 tag")
        ok("# Role,Station Name,Model Id,IP Address,PN Number (empty:last IP Octet)" in s, "descriptive header")
        ok("Plc,n1,CPU1,192.168.50.1,,Subnet50,,=S1_IODevices" in s, "a station data row")
        m = open(mpath, "rb").read().decode("utf-8")
        ok(m.startswith("#!format=2,,,,,,,\r\n"), "Modules format-2 tag")
        ok("n6,1,-C1,DI16,0,0,PotentialGroup=1 | Ch(0).Filter=1 | Ch(1).Filter=1,DI 16x24VDC" in m)


# --- phase wiring -------------------------------------------------------------------------- #

def test_phase_registered():
    p = registry().get(700)
    eq(p.number, 700); eq(p.key, "hardware"); eq(p.requires, (300,))
    eq([s.number for s in p.sub_phases], [710, 720])
    eq([b.number for b in p.buttons], [710, 720, 730])


def test_phase_run():
    with tempfile.TemporaryDirectory() as d:
        ctx = PipelineContext(params={}, out_root=os.path.join(d, "out"), emit=lambda *_a, **_k: None)
        ctx.rows = _rows()
        ctx.device_db = _dtd()                       # inject so no DTD file is needed
        res = p700_hardware.run(ctx)
        ok(res.ok)
        hw = config.out_path(ctx.out_root, "hardware_dir")
        eq(res.artifacts["hardware_dir"], hw)
        ok(os.path.exists(os.path.join(hw, "Stations.csv")))
        ok(os.path.exists(os.path.join(hw, "Modules.csv")))


if __name__ == "__main__":
    raise SystemExit(run("hardware", [
        ("role", test_role),
        ("parse_address", test_parse_address),
        ("merge_params_override", test_merge_params_override),
        ("resolve_addr_template", test_resolve_addr_template),
        ("extract_stations_and_modules", test_extract_stations_and_modules),
        ("extract_auto_plug_skipped", test_extract_auto_plug_skipped),
        ("station_io_addr_and_ag_override", test_station_io_addr_and_ag_override),
        ("missing_dtd_error_and_switch_warning", test_missing_dtd_error_and_switch_warning),
        ("format2_output", test_format2_output),
        ("phase_registered", test_phase_registered),
        ("phase_run", test_phase_run),
    ]))
