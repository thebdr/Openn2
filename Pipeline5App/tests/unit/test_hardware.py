"""Phase 700 (Hardware) build - the helpers, the single-pass extract (auto-plug skip, PotentialGroup,
by-type channel params, default cards), the missing-DTD FAIL / switch WARN findings, and the table fill.
Pure + data-independent (the build()/CSV projection are verified by the data-dependent parity script)."""
import os
import tempfile

from _harness import run, eq, ok
from pipeline5.truth.database import Database
from pipeline5.systems.plc_based.siemens_s7 import profinet_hardware as hardware
from pipeline5.systems.plc_based.siemens_s7 import hardware_csv_export as hardware_csv


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
         "functional_unit": "=S1", "slot": "-K1", "type_hw": "", "bit": "", "connector": "-X1",
         "source_sheet": "NS50", "source_row": 2},
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
    eq(plc["group_path"], "", "the Plc head stays at the TIA root (empty Group - OP honors grouping)")
    eq(stations[1]["group_path"], "=S1_IODevices", "an IoDevice keeps the FU device group")
    eq(plc["connector"], "-X1", "the head row's connector cell, verbatim")
    eq(stations[1]["connector"], "", "no connector on the head row -> empty")
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


def test_shipped_sfb_v2_station_addresses():
    """C-028: the SHIPPED DeviceTypesDatabase places an SFB-PN V2's three data submodules at the station's own
    I/O-List base (FS data +0, Diagnosis and FB-Interface +6, Functional data +12 - inputs and outputs), so the
    I/O List's pin rows (X1 at the base, X2 +1, DI +7, the DO lamp at the output base) land on the hardware.
    The FVT shape: a compact GSD station, its signal rows carrying no card slot of their own."""
    from pipeline5.config.loaders import load_device_types_db
    dtd = load_device_types_db()
    rec = dtd["by_id"].get("103040357")
    ok(rec is not None and rec["dev_type"] == "IoDevice", "the SFB V2 is a shipped IoDevice")
    head = {"script_type": "PA", "type_hw": "PA", "part_no": "103040357", "profinet_name": "n0085-es-k1",
            "profinet_ip": "192.168.20.85", "functional_unit": "=ES", "slot": "-K1", "bit": "",
            "source_sheet": "NET", "source_row": 985}
    pins = [("-K1", "I1484.0"), ("", "I1485.0"), ("", "I1491.0"), ("", "Q1484.0"),
            ("-K1", "I1484.7"), ("", "I1485.7"), ("", "I1491.7"), ("", "Q1484.7")]
    rows = [head] + [{"script_type": "", "part_no": "103040357", "slot": s, "bit": b, "source_sheet": "NET",
                      "source_row": 986 + i} for i, (s, b) in enumerate(pins)]
    stations, modules, findings = hardware.extract(rows, dtd)
    eq(len(stations), 1, "one station")
    eq([f.type for f in findings if f.severity == "FAIL"], [], "the model is known: no hw_device_not_in_dtd")
    eq(modules, [], "a compact station: no card rows (its pin rows are auto-plugged)")
    got = {p.split("=", 1)[0].strip(): p.split("=", 1)[1].strip()
           for p in stations[0]["custom_parameters"].split("|") if "StartAddress" in p}
    eq(got, {"Item(1).Item(2).Item(0).Addr(0).StartAddress": "1484", "Item(1).Item(2).Item(0).Addr(1).StartAddress": "1484",
             "Item(1).Item(2).Item(2).Addr(0).StartAddress": "1490", "Item(1).Item(2).Item(2).Addr(1).StartAddress": "1490",
             "Item(1).Item(2).Item(1).Addr(0).StartAddress": "1496", "Item(1).Item(2).Item(1).Addr(1).StartAddress": "1496"},
       "FS data at the base, Diagnosis +6, Functional +12 - inputs and outputs")
    defaults = {e.split("=", 1)[0].strip(): e.split("=", 1)[1].strip() for e in rec["params"].split("|") if "=" in e}
    eq(defaults, {"Item(1).Item(2).Item(0).Failsafe_FDestinationAddress": "IP[3]",
                  "Item(1).Item(2).Item(0).Failsafe_FMonitoringtime": "250",
                  "Item(1).Item(2).Item(0).Failsafe_FParameterSignatureIndividualParameters": "123358913",
                  "Item(1).Item(2).Item(0).PrmData(1-8)": "06 01 01"},
       "the model-wide F-parameter defaults the importer applies (F-destination = the IP's last octet)")


def _sfb_rows(pins, head_extra=None):
    head = {"script_type": "PA", "type_hw": "PA", "part_no": "103040357", "profinet_name": "n0085-es-k1",
            "profinet_ip": "192.168.20.85", "functional_unit": "=ES", "slot": "-K1", "bit": "",
            "source_sheet": "NET", "source_row": 985, "source_cell": "NET!O985"}
    head.update(head_extra or {})
    return [head] + [{"script_type": t, "part_no": pn, "slot": sl, "bit": bit, "source_sheet": "NET",
                      "source_row": 986 + i} for i, (sl, bit, t, pn) in enumerate(pins)]


def _start_addresses(station):
    return {e.split("=", 1)[0].strip(): e.split("=", 1)[1].strip()
            for e in station["custom_parameters"].split("|") if "StartAddress" in e}


def test_shipped_fdi_dd_channel_block():
    """C-028 (the database's F-DI door-diagnosis block): a DD row on the shipped 6ES7136-6BA01-0CA0 card gets
    the card's DD block at its own channel - sensor evaluation off, sensor supply 8."""
    from pipeline5.config.loaders import load_device_types_db
    rows = _sfb_rows([("-K30004", "I10.0", "DI1/2", "6ES7136-6BA01-0CA0"),
                      ("-K30004", "I10.2", "DD", "6ES7136-6BA01-0CA0")])
    _stations, modules, _f = hardware.extract(rows, load_device_types_db())
    eq(len(modules), 1, "one F-DI card")
    text = " | ".join(str(v) for v in modules[0].values())
    ok("Ch(2).Failsafe_SensorEvaluation=0" in text and "Ch(2).Failsafe_SensorSupply=8" in text,
       "the DD block at channel 2")
    ok("Ch(0).Failsafe_SensorSupply=8" in text, "the DI1/2 block at channel 0")


def test_sfb_without_output_rows_drops_the_q_entries():
    """C-028 (refute round 1): a station with no output row cannot place its `%Q%` entries - they are DROPPED
    (never a literal `%Q%` the importer cannot convert) with a hw_addr_unresolved WARN; the inputs still land."""
    from pipeline5.config.loaders import load_device_types_db
    rows = _sfb_rows([("-K1", "I1484.0", "", "103040357"), ("", "I1485.0", "", "103040357")])
    stations, _m, findings = hardware.extract(rows, load_device_types_db())
    ok("%Q%" not in stations[0]["custom_parameters"] and "%I%" not in stations[0]["custom_parameters"],
       "no unresolved template reaches Stations.csv")
    eq(_start_addresses(stations[0]), {"Item(1).Item(2).Item(0).Addr(0).StartAddress": "1484",
                                       "Item(1).Item(2).Item(2).Addr(0).StartAddress": "1490",
                                       "Item(1).Item(2).Item(1).Addr(0).StartAddress": "1496"},
       "the input entries placed, the output ones dropped")
    warn = [f for f in findings if f.type == "hw_addr_unresolved"]
    eq([f.severity for f in warn], ["WARN"], "one WARN for the station")
    ok("output" in warn[0].detail and "3 start-address entries" in warn[0].detail, warn[0].detail)
    eq(warn[0].location, "NET!O985", "it links the head's I/O-List row")


def test_sfb_base_is_the_lowest_row_and_col_ag_overrides():
    """C-028 boundary (documented): the station base is its LOWEST I/O-List address per direction - a box whose
    X1 (+0) row is missing shifts its layout; the head's Hardware Parameters (col AG) override an entry."""
    from pipeline5.config.loaders import load_device_types_db
    pins = [("-K1", "I1485.0", "", "103040357"), ("", "I1491.0", "", "103040357"), ("", "Q1484.0", "", "103040357")]
    stations, _m, _f = hardware.extract(_sfb_rows(pins), load_device_types_db())
    eq(_start_addresses(stations[0])["Item(1).Item(2).Item(0).Addr(0).StartAddress"], "1485",
       "no +0 input row: the lowest input row is taken as the base")
    fix = {"hardware_params": "Item(1).Item(2).Item(0).Addr(0).StartAddress = 1484"}
    stations, _m, _f = hardware.extract(_sfb_rows(pins, fix), load_device_types_db())
    eq(_start_addresses(stations[0])["Item(1).Item(2).Item(0).Addr(0).StartAddress"], "1484",
       "the head's col-AG entry overrides the template's")


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


def test_duplicate_ip_stations_skipped():
    # the FVX_PL4_Pilot case: a redundant-CPU pair documents Master + Backup on ONE IP (110's
    # ip_duplicated deliberately exempts .1-suffixed IPs) - only the FIRST station per IP is generated.
    rows = [
        {"script_type": "", "type_hw": "PA", "part_no": "COUPLER", "profinet_name": "n1",
         "profinet_ip": "192.168.50.1", "functional_unit": "=S1", "slot": "-K1", "bit": "",
         "source_sheet": "NS", "source_row": 2, "source_cell": "NS!O2",
         "description_module": "CPU 1518F (Master)"},
        {"script_type": "", "type_hw": "PA", "part_no": "COUPLER", "profinet_name": "n2",
         "profinet_ip": "192.168.50.1", "functional_unit": "=S1", "slot": "-K2", "bit": "",
         "source_sheet": "NS", "source_row": 3, "source_cell": "NS!O3",
         "description_module": "CPU 1518F (Backup)"},
        {"script_type": "A", "part_no": "DI16", "slot": "-C9", "bit": "I90.0",
         "source_sheet": "NS", "source_row": 4},                       # the skipped head's card row
        {"script_type": "", "type_hw": "PA", "part_no": "COUPLER", "profinet_name": "n3",
         "profinet_ip": "192.168.50.1", "functional_unit": "=S1", "slot": "-K3", "bit": "",
         "source_sheet": "NS", "source_row": 5, "source_cell": "NS!O5",
         "description_module": "THIRD DEVICE"},
        {"script_type": "", "type_hw": "PA", "part_no": "COUPLER", "profinet_name": "n6",
         "profinet_ip": "192.168.50.6", "functional_unit": "=S1", "slot": "-K6", "bit": "",
         "source_sheet": "NS", "source_row": 6, "source_cell": "NS!O6"},
    ]
    stations, modules, findings = hardware.extract(rows, _dtd())
    eq([s["station_name"] for s in stations], ["n1", "n6"], "only the FIRST station per IP is generated")
    ok(all(m["station_name"] in ("n1", "n6") for m in modules),
       "a skipped head generates NO cards (its signal rows are dropped with it)")
    dups = [f for f in findings if f.type == "hw_duplicate_ip"]
    eq([f.severity for f in dups], ["INFO", "WARN"],
       "'backup' in the module description -> INFO (expected redundancy), else WARN")
    eq((dups[0].location, dups[0].location2), ("NS!O3", "NS!O2"),
       "location = the skipped head's row, location2 = the generated station's")
    eq((dups[1].location, dups[1].location2), ("NS!O5", "NS!O2"))
    ok("duplicate IP 192.168.50.1" in dups[0].detail)
    ok("only the first ('n1') is generated" in dups[0].detail)
    ok(not hardware.run.has_blocking(dups), "the skip never halts the build")


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
        ok(s.startswith("#!openn\r\n#! kind: hw/stations\r\n#! schema: 2\r\n#! producer: Pipeline5 5.0 (phase 700)\r\n"),
           "the contract-v1 header opens the file: hw/stations, schema 2 (= format 2), the producer")
        ok("\r\n#! run: " in s and "\r\n#! target: Devices & networks\r\n" in s and "\r\n#!end\r\n# Role," in s,
           "the run id, the TIA folder, then the descriptive header comment right after #!end")
        ok("#!format=" not in s, "the bare format tag is gone (schema carries the format number)")
        ok("# Role,Station Name,Model Id,IP Address,PN Number (empty:last IP Octet)" in s, "descriptive header")
        ok("Group = folder/subfolder/...,Connector," in s, "the header names the appended Connector column")
        ok("Plc,n1,CPU1,192.168.50.1,,Subnet50,,,-X1" in s,
           "the Plc data row: EMPTY Group (root), connector appended LAST")
        ok(",=S1_IODevices," in s, "the IoDevice row keeps the FU device group")
        m = open(res["modules_path"], "rb").read().decode("utf-8")
        ok(m.startswith("#!openn\r\n#! kind: hw/modules\r\n#! schema: 2\r\n"), "Modules: the hw/modules header, schema 2")
        ok("n6,1,-C1,DI16,0,0,PotentialGroup=1 | Ch(0).Filter=1 | Ch(1).Filter=1,DI 16x24VDC" in m,
           "a module data row (PotentialGroup + by-type channel params)")


def test_sfb_base_is_the_lowest_row_whatever_the_order():
    """C-028 refute round 2: the base is the LOWEST address per direction, not the first row listed."""
    from pipeline5.config.loaders import load_device_types_db
    pins = [("", "Q1485.0", "", "103040357"), ("", "Q1484.0", "", "103040357"),
            ("", "I1485.0", "", "103040357"), ("-K1", "I1484.0", "", "103040357")]
    stations, _m, _f = hardware.extract(_sfb_rows(pins), load_device_types_db())
    got = _start_addresses(stations[0])
    eq((got["Item(1).Item(2).Item(0).Addr(0).StartAddress"], got["Item(1).Item(2).Item(0).Addr(1).StartAddress"]),
       ("1484", "1484"), "the lowest input and output rows are the bases, listed last")


def test_sfb_without_input_rows_drops_the_i_entries():
    """C-028 refute round 2: the mirror case - a station with only output rows drops its `%I%` entries and its
    WARN names the INPUT direction only."""
    from pipeline5.config.loaders import load_device_types_db
    rows = _sfb_rows([("-K1", "Q1484.0", "", "103040357")])
    stations, _m, findings = hardware.extract(rows, load_device_types_db())
    ok("%I%" not in stations[0]["custom_parameters"], "no literal %I% reaches Stations.csv")
    eq(_start_addresses(stations[0]), {"Item(1).Item(2).Item(0).Addr(1).StartAddress": "1484",
                                       "Item(1).Item(2).Item(2).Addr(1).StartAddress": "1490",
                                       "Item(1).Item(2).Item(1).Addr(1).StartAddress": "1496"},
       "the output entries placed, the input ones dropped")
    warn = [f for f in findings if f.type == "hw_addr_unresolved"]
    eq(len(warn), 1, "one WARN")
    ok("no input row" in warn[0].detail and "output" not in warn[0].detail, warn[0].detail)


def test_col_ag_placing_a_dropped_entry_is_not_left_to_tia():
    """C-028 refute round 2: an entry the head's Hardware Parameters (col AG) set reaches Stations.csv and is not
    counted as left to TIA; when AG sets every dropped entry there is no WARN at all."""
    from pipeline5.config.loaders import load_device_types_db
    dtd = load_device_types_db()
    q0 = "Item(1).Item(2).Item(0).Addr(1).StartAddress"
    pins = [("-K1", "I1484.0", "", "103040357")]
    stations, _m, findings = hardware.extract(_sfb_rows(pins, {"hardware_params": f"{q0} = 1484"}), dtd)
    eq(_start_addresses(stations[0]).get(q0), "1484", "the AG entry is placed")
    warn = [f for f in findings if f.type == "hw_addr_unresolved"]
    ok(len(warn) == 1 and "2 start-address entries" in warn[0].detail, [f.detail for f in warn])
    every = " | ".join(f"Item(1).Item(2).Item({i}).Addr(1).StartAddress = {a}" for i, a in ((0, 1484), (2, 1490), (1, 1496)))
    _s, _m, findings = hardware.extract(_sfb_rows(pins, {"hardware_params": every}), dtd)
    eq([f for f in findings if f.type == "hw_addr_unresolved"], [], "AG places every dropped entry -> no WARN")


def test_resolve_addr_template_ignores_case():
    """C-028 refute round 2: a hand-typed lower-case placeholder resolves like the upper-case one (the drop
    check already ignored case - a `%i%` was dropped with a false 'no input row')."""
    eq(hardware._resolve_addr_template("%i%+6 | %q%", 10, 20), "16 | 20")


def test_project_device_types_db_is_what_700_reads_and_places():
    """C-028 refute round 3: a project whose params name its own DeviceTypesDatabase (`device_types_db`) gets ITS
    values - phase 700 reads it, and 700b places a copy beside Stations.csv for the importer (which reads a local
    one first); with no param nothing is placed, and a stray local copy is reported (it would override the
    shared one for the importer), never deleted."""
    from pipeline5 import config
    from pipeline5.config.loaders import load_device_types_db
    from pipeline5.config.paths import DEVICE_TYPES_DB_DEFAULT
    from pipeline5.truth.signals import signals_table
    shared = open(DEVICE_TYPES_DB_DEFAULT, encoding="utf-8-sig").read()
    assert "<DI1/2>Ch(#).Failsafe_SensorSupply=8<DI1/2>" in shared
    rows = _sfb_rows([("-K30004", "I10.0", "DI1/2", "6ES7136-6BA01-0CA0")])
    original, original_db = config.load_params, config.database_dir
    with tempfile.TemporaryDirectory() as d:
        config.database_dir = lambda: d             # build() saves its tables - never into the repo
        own = os.path.join(d, "MyDeviceTypes.csv")
        with open(own, "w", encoding="utf-8") as f:
            f.write(shared.replace("<DI1/2>Ch(#).Failsafe_SensorSupply=8<DI1/2>",
                                   "<DI1/2>Ch(#).Failsafe_SensorEvaluation=0<DI1/2>"))
        sig = signals_table(sorted({k for r in rows for k in r}))
        for r in rows:
            sig.add(**r)
        out = os.path.join(d, "hw")
        try:
            config.load_params = lambda path=None: {"device_types_db": own}
            db, _f = hardware.build(Database([sig]))
            text = " | ".join(str(v) for v in db["hardware_modules"].rows[0].values())
            ok("Ch(0).Failsafe_SensorEvaluation=0" in text and "SensorSupply" not in text,
               f"700 read the project's database: {text}")
            res = hardware_csv.project(db, out_dir=out)
            eq(open(res["device_types_db"], encoding="utf-8").read(), open(own, encoding="utf-8").read(),
               "700b placed the project's database beside Stations.csv")
            config.load_params = lambda path=None: {}
            res = hardware_csv.project(db, out_dir=out)
            eq(res["device_types_db"], "", "no param: nothing placed")
            eq([(f.type, f.severity) for f in res["findings"]], [("hw_local_dtd", "WARN")], "the stray copy reported")
            ok(os.path.isfile(os.path.join(out, "DeviceTypesDatabase.csv")), "never deleted")
        finally:
            config.load_params, config.database_dir = original, original_db
    eq(load_device_types_db({"device_types_db": ""})["by_id"]["103040357"]["dev_type"], "IoDevice",
       "a blank param reads the shared database")


def test_col_ag_keys_matched_the_importers_way():
    """C-028 refute round 3: col AG sets a dropped entry whatever its key's case or spacing, and through one
    `(a-b)` range - the importer reads it so; an AG entry with no value sets nothing."""
    from pipeline5.config.loaders import load_device_types_db
    dtd = load_device_types_db()
    pins = [("-K1", "I1484.0", "", "103040357")]

    def left(ag):
        _s, _m, f = hardware.extract(_sfb_rows(pins, {"hardware_params": ag}), dtd)
        w = [x.detail for x in f if x.type == "hw_addr_unresolved"]
        return w[0] if w else ""
    ok("2 start-address entries" in left("Item(1).Item(2).Item(0).Addr(0-1).StartAddress = 1484"), "a range")
    ok("2 start-address entries" in left("item(1).item(2).item(0).addr(1).StartAddress = 1484"), "lower case")
    ok("2 start-address entries" in left("Item(1).Item(2).Item(0).Addr(1) . StartAddress = 1484"), "spacing")
    ok("3 start-address entries" in left("Item(1).Item(2).Item(0).Addr(1).StartAddress ="), "no value: still left")


def test_lowercase_placeholder_without_rows_is_dropped():
    """C-028 refute round 3: a hand-typed lower-case `%q%` whose direction has no row is dropped and warned like
    `%Q%` - never a literal placeholder in Stations.csv."""
    dtd = {"by_id": {"BOX": _dtd_rec("BOX", "IoDevice", io_addr="Item(0).Addr(0).StartAddress = %i% | "
                                     "Item(0).Addr(1).StartAddress = %q% | Item(1).Addr(1).StartAddress = %q%+2")},
           "default_cards": {}}
    rows = [{"script_type": "PA", "type_hw": "PA", "part_no": "BOX", "profinet_name": "n1", "profinet_ip": "1.2.3.4",
             "functional_unit": "=X", "slot": "-K1", "bit": "", "source_sheet": "NET", "source_row": 2},
            {"script_type": "", "part_no": "BOX", "slot": "-K1", "bit": "I20.0", "source_sheet": "NET", "source_row": 3}]
    stations, _m, findings = hardware.extract(rows, dtd)
    ok("%" not in stations[0]["custom_parameters"], stations[0]["custom_parameters"])
    eq(_start_addresses(stations[0]), {"Item(0).Addr(0).StartAddress": "20"}, "the input placed")
    warn = [f.detail for f in findings if f.type == "hw_addr_unresolved"]
    ok(len(warn) == 1 and "2 start-address entries" in warn[0], warn)


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
        ("duplicate_ip_stations_skipped", test_duplicate_ip_stations_skipped),
        ("fill_tables_and_uids", test_fill_tables_and_uids),
        ("format2_projection", test_format2_projection),
        ("shipped_sfb_v2_station_addresses", test_shipped_sfb_v2_station_addresses),
        ("shipped_fdi_dd_channel_block", test_shipped_fdi_dd_channel_block),
        ("sfb_without_output_rows_drops_the_q_entries", test_sfb_without_output_rows_drops_the_q_entries),
        ("sfb_base_is_the_lowest_row_and_col_ag_overrides", test_sfb_base_is_the_lowest_row_and_col_ag_overrides),
        ("sfb_base_is_the_lowest_row_whatever_the_order", test_sfb_base_is_the_lowest_row_whatever_the_order),
        ("sfb_without_input_rows_drops_the_i_entries", test_sfb_without_input_rows_drops_the_i_entries),
        ("col_ag_placing_a_dropped_entry_is_not_left_to_tia", test_col_ag_placing_a_dropped_entry_is_not_left_to_tia),
        ("resolve_addr_template_ignores_case", test_resolve_addr_template_ignores_case),
        ("project_device_types_db_is_what_700_reads_and_places", test_project_device_types_db_is_what_700_reads_and_places),
        ("col_ag_keys_matched_the_importers_way", test_col_ag_keys_matched_the_importers_way),
        ("lowercase_placeholder_without_rows_is_dropped", test_lowercase_placeholder_without_rows_is_dropped),
    ]))
