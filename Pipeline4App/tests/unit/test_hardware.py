"""Phase 700 (Hardware) build - the helpers, the single-pass extract (auto-plug skip, PotentialGroup,
by-type channel params, default cards), the missing-DTD FAIL / switch WARN findings, and the table fill.
Pure + data-independent (the build()/CSV projection are verified by the data-dependent parity script)."""
import os
import tempfile

from _harness import run, eq, ok
from pipeline4.core.database import Database
from pipeline4.domain import hardware, hardware_csv


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
         "functional_unit": "=S1", "slot": "-K1", "type_hw": "", "bit": "", "source_sheet": "NS50", "source_row": 2},
        {"script_type": "", "type_hw": "PA", "part_no": "COUPLER", "profinet_name": "n6",
         "profinet_ip": "192.168.50.6", "functional_unit": "=S1", "slot": "-K6", "bit": "",
         "source_sheet": "NS50", "source_row": 3},
        {"script_type": "A", "part_no": "DI16", "slot": "-C1", "bit": "I0.0", "source_sheet": "NS50", "source_row": 4},
        {"script_type": "A", "part_no": "DI16", "slot": "-C1", "bit": "I0.1", "source_sheet": "NS50", "source_row": 5},
        {"script_type": "A", "part_no": "DQ16", "slot": "-C2", "bit": "Q0.0", "source_sheet": "NS50", "source_row": 6},
        {"script_type": "A", "part_no": "DI16", "slot": "-K6", "bit": "I8.0", "source_sheet": "NS50", "source_row": 7},  # auto-plug (head tag)
    ]


# --- helpers ------------------------------------------------------------------------------------- #
def test_role():
    eq(hardware._role({"script_type": "PLC"}), "Plc")
    eq(hardware._role({"script_type": "PlcCardCm"}), "PlcCardCm")
    eq(hardware._role({"type_hw": "PA"}), "IoDevice")
    eq(hardware._role({"type_hw": "A"}), None)
    eq(hardware._role({"script_type": "A", "type_hw": ""}), None)


def test_parse_address():
    eq(hardware.parse_address("I20.3"), ("I", 20, 3))
    eq(hardware.parse_address("Q0.0"), ("Q", 0, 0))
    eq(hardware.parse_address(""), None)
    eq(hardware.parse_address("PA"), None)


def test_merge_params_override():
    eq(hardware._merge_params("a=1|b=2", "b=3|c=4"), "a=1 | b=3 | c=4", "later blob overrides by key")
    eq(hardware._merge_params("PotentialGroup=1", "", "x=9"), "PotentialGroup=1 | x=9")
    eq(hardware._merge_params("flag", "flag"), "flag", "valueless token kept once")


def test_resolve_addr_template():
    eq(hardware._resolve_addr_template("%I%", 10, None), "10")
    eq(hardware._resolve_addr_template("%I% + 2", 10, None), "12")
    eq(hardware._resolve_addr_template("%Q%", None, 20), "20")
    eq(hardware._resolve_addr_template("%I%", None, None), "%I%", "no base -> left as-is")


# --- extract ------------------------------------------------------------------------------------- #
def test_extract_stations_and_modules():
    stations, modules, findings = hardware.extract(_rows(), _dtd())
    eq(findings, [], "all models in the DTD -> no findings")
    eq([s["role"] for s in stations], ["Plc", "IoDevice"])
    plc = stations[0]
    eq(plc["station_name"], "n1")
    eq(plc["model_id"], "CPU1")
    eq(plc["subnet"], "Subnet50")
    eq(plc["group_path"], "=S1_IODevices")
    # modules for the IoDevice n6: cards -C1, -C2 (the -K6 head-tag card is auto-plugged), + default PS card
    names = [(m["slot"], m["module_name"], m["model_id"]) for m in modules]
    eq(names, [(1, "-C1", "DI16"), (2, "-C2", "DQ16"), (3, "COUPLER:PS", "COUPLER:PS")])
    c1 = modules[0]
    eq(c1["station_name"], "n6")
    eq((c1["i_addr"], c1["q_addr"]), (0, 0))
    eq(c1["comment"], "DI 16x24VDC")
    eq(c1["custom_parameters"], "PotentialGroup=1 | Ch(0).Filter=1 | Ch(1).Filter=1",
       "first card PotentialGroup + per-channel by-type params")
    eq(modules[1]["custom_parameters"], "", "2nd card: no PotentialGroup, no by-type")
    eq(modules[2]["custom_parameters"], "", "default card carries no params (DTD col-5 -> OP4)")


def test_extract_auto_plug_skipped():
    _s, modules, _f = hardware.extract(_rows(), _dtd())
    ok(all(m["module_name"] != "-K6" for m in modules), "the card whose slot == the device tag is auto-plugged")


def test_station_io_addr_and_ag_override():
    rows = [
        {"script_type": "", "type_hw": "PA", "part_no": "COUPLER", "profinet_name": "n9",
         "profinet_ip": "192.168.51.9", "functional_unit": "=S2", "slot": "-K9",
         "hardware_params": "Foo=override", "bit": "", "source_sheet": "NS", "source_row": 2},
        {"script_type": "A", "part_no": "DI16", "slot": "-C1", "bit": "I40.0", "source_sheet": "NS", "source_row": 3},
    ]
    dtd = _dtd()
    dtd["by_id"]["COUPLER"]["io_addr_params"] = "Addr.Start=%I%"
    stations, _m, _f = hardware.extract(rows, dtd)
    eq(stations[0]["subnet"], "Subnet51")
    eq(stations[0]["custom_parameters"], "Addr.Start=40 | Foo=override",
       "%I% -> device start byte (40), then col-AG appended last")


def test_missing_dtd_fail_and_switch_warning():
    rows = [
        {"script_type": "PLC", "part_no": "UNKNOWN_CPU", "profinet_name": "n1",
         "source_sheet": "NS", "source_row": 2, "device": "-K1", "source_cell": "NS!A2"},
        {"script_type": "PLC", "part_no": "SW1", "description_module": "MANAGED SWITCH",
         "profinet_name": "n2", "source_sheet": "NS", "source_row": 3, "device": "-K2",
         "source_cell": "NS!A3"},
    ]
    stations, _m, findings = hardware.extract(rows, _dtd())
    eq(stations, [], "neither head is generatable")
    eq(sorted((f.type, f.severity) for f in findings),
       [("hw_device_not_in_dtd", "FAIL"), ("hw_switch_not_in_dtd", "WARN")],
       "a non-switch missing head is a FAIL; a switch is a WARN")
    ok(all(f.phase == 700 for f in findings), "phase 700")
    ok(any("UNKNOWN_CPU" in f.detail for f in findings))
    # the log link contract: a doc-row finding carries location=source_cell (Sheet!Cell) + the
    # workbook doc; the device name lives in the DETAIL (it used to squat in the location text)
    eq(sorted(f.location for f in findings), ["NS!A2", "NS!A3"],
       "doc-row findings point at the exact source cell (clickable)")
    ok(all(f.doc for f in findings), "…and carry the workbook for the GUI link resolver")
    ok(any("(n2)" in f.detail for f in findings), "the device name moved into the detail")
    # rows WITHOUT source_cell (older stagings) fall back to the descriptive text - never crash
    bare = [{"script_type": "PLC", "part_no": "UNKNOWN_CPU", "source_sheet": "NS", "source_row": 9}]
    _s, _m2, fb = hardware.extract(bare, _dtd())
    eq(fb[0].location, "[NS] row 9", "the no-source_cell fallback keeps the old text (no link)")
    eq(fb[0].doc, "", "…and carries no doc (nothing to resolve)")


# --- table fill ---------------------------------------------------------------------------------- #
def test_fill_tables_and_uids():
    stations, modules, _f = hardware.extract(_rows(), _dtd())
    stab, mtab = hardware.hardware_stations_table(), hardware.hardware_modules_table()
    hardware._fill_stations(stab, stations)
    hardware._fill_modules(mtab, modules)
    eq(len(stab), 2, "2 stations")
    eq(len(mtab), 3, "3 modules")
    eq(stab.duplicate_uids(), set(), "distinct station uids")
    eq(mtab.duplicate_uids(), set(), "distinct module uids")
    first = mtab.rows[0]
    eq((first["slot"], first["i_addr"], first["q_addr"]), ("1", "0", "0"), "slot/addr stored as text")


# --- 700b: the format-2 projection --------------------------------------------------------------- #
def _built_db():
    stations, modules, _f = hardware.extract(_rows(), _dtd())
    stab, mtab = hardware.hardware_stations_table(), hardware.hardware_modules_table()
    hardware._fill_stations(stab, stations)
    hardware._fill_modules(mtab, modules)
    return Database([stab, mtab])


def test_format2_projection():
    with tempfile.TemporaryDirectory() as d:
        res = hardware_csv.project(_built_db(), out_dir=d)
        eq((res["stations"], res["modules"]), (2, 3))
        eq(res["findings"], [], "a pure projection emits no findings")
        sraw = open(res["stations_path"], "rb").read()
        ok(not sraw.startswith(b"\xef\xbb\xbf"), "no BOM (matches the reference)")
        ok(sraw.count(b"\n") > 0 and sraw.count(b"\n") == sraw.count(b"\r\n"), "CRLF only")
        s = sraw.decode("utf-8")
        ok(s.startswith("#!format=2,,,,,,,,\r\n"), "Stations format-2 tag")
        ok("# Role,Station Name,Model Id,IP Address,PN Number (empty:last IP Octet)" in s, "descriptive header")
        ok("Plc,n1,CPU1,192.168.50.1,,Subnet50,,=S1_IODevices" in s, "a station data row")
        m = open(res["modules_path"], "rb").read().decode("utf-8")
        ok(m.startswith("#!format=2,,,,,,,\r\n"), "Modules format-2 tag")
        ok("n6,1,-C1,DI16,0,0,PotentialGroup=1 | Ch(0).Filter=1 | Ch(1).Filter=1,DI 16x24VDC" in m,
           "a module data row (PotentialGroup + by-type channel params)")


if __name__ == "__main__":
    import sys
    sys.exit(run("hardware", [
        ("role", test_role),
        ("parse_address", test_parse_address),
        ("merge_params_override", test_merge_params_override),
        ("resolve_addr_template", test_resolve_addr_template),
        ("extract_stations_and_modules", test_extract_stations_and_modules),
        ("extract_auto_plug_skipped", test_extract_auto_plug_skipped),
        ("station_io_addr_and_ag_override", test_station_io_addr_and_ag_override),
        ("missing_dtd_fail_and_switch_warning", test_missing_dtd_fail_and_switch_warning),
        ("fill_tables_and_uids", test_fill_tables_and_uids),
        ("format2_projection", test_format2_projection),
    ]))
