"""The web diagnosis app's plant model (phase 650, C-050, `webui_model.build_plant`) on a small synthetic Database
with the SHIPPED webui config: the exact quoted variable names, the poll set, the family + index grouping and the
anchor, the node-failed resolution, a further kind enabled by config alone, the polarity INFO, the most specific
member rule, the sorter's area by ordinal, the positions' stale WARN / unplaced INFO, the drawing measure and the
template bundle."""
import copy
import os
import struct
import tempfile

from _harness import run, eq, ok, raises
from pipeline5 import config
from pipeline5.systems.plc_based.siemens_s7.safety import webui_model as model
from pipeline5.systems.plc_based.siemens_s7.safety import webui_project as project

DIAG = {"alarm_dwords": ["ALARM1", "ALARM2"], "warning_dwords": ["WARNING1", "WARNING2"],
        "instance_template": "S1.CABINET{$index}.{$role}", "default_variant": 1}
NODE_BINDING = '"PROFINET_NODES_ALARM"."n0002-io 10.0.0.2"'


def _sig(uid, st, index="", **cells):
    row = {"uid": uid, "script_type": st, "index": index, "desc_l1": "", "functional_unit": "", "location": "",
           "device": "", "iol_FLD": "", "matrix_areas": "", "profinet_name": "", "profinet_ip": "",
           "name_in_tagtable": "", "tagtable": "", "bit": "", "plc_binding": ""}
    row.update(cells)
    return row


def _mem(db, member, source, struct=""):
    return {"db_name": db, "member": member, "source": source, "struct": struct}


def _entry(signal, cabinet, bit, fl="false", warning="false", text="", source="io"):
    return {"source": source, "source_signal": signal, "cabinet": str(cabinet), "bit": str(bit), "is_warning": warning,
            "fl_value": fl, "in_binding": "", "rule_name": "", "diag_columns": '{"Diag Desc": "%s"}' % text}


def _database():
    signals = [
        _sig("p0", "Plc", "0001", profinet_name="n0001-cpu", profinet_ip="10.0.0.1"),
        _sig("pa1", "PA", "0002", profinet_name="n0002-io", profinet_ip="10.0.0.2", iol_FLD="=TRIC-AEC01-K1",
             desc_l1="CPU SAFETY", plc_binding=NODE_BINDING),
        _sig("el1", "EL", "0001", iol_FLD="=ES-0001", name_in_tagtable="Emergency Push Button Lamp [ =ES-0001 ]",
             tagtable="EMERGENCY_PushButtons", bit="Q1.0"),
        _sig("e1", "E", "0001", iol_FLD="=ES-0001", functional_unit="=ES", device="-0001",
             desc_l1="EMERGENCY PUSH BUTTON PRESSED", matrix_areas='["AREA 1_TRIB", "AREA 1"]',
             name_in_tagtable="Emergency Push Button [ =ES-0001 ]", tagtable="EMERGENCY_PushButtons", bit="I1.0"),
        _sig("ki1", "KI1/2", "0044", iol_FLD="=TRIB-MA01-K50001", desc_l1="FEEDBACK OF SAFETY RELAY FAULT"),
        _sig("kq1", "KQ1/2", "0044", iol_FLD="=TRIB-MA01-K50001", matrix_areas=["AREA 1"]),
        _sig("kq2", "KQ2/2", "0044", iol_FLD="=TRIB-MA01-K50002"),
        _sig("kb1", "KB", "", iol_FLD="=TRIB-MA01-K50001"),                   # a QBAD: no index, no device
        _sig("n1", "N1/2", "0001", iol_FLD="=TRIB-EN02-B1R", desc_l1="SAFETY ENCODER FAILURE"),
        _sig("f1", "F1/2", "0001", iol_FLD="=TRIC-FA01-B1", desc_l1="FIRE ALARM"),
    ]
    members = [
        _mem("01_Pushbutton", "AlwaysTRUE", "seed"),
        _mem("01_Pushbutton", "Emergency Push Button [ =ES-0001 ]", "e1"),
        _mem("03_FDBACK", "Contactor Feedback Error [ =TRIB-MA01-K50001 ]", "kq1"),
        _mem("04_SPEED", "Safety Encoder 0001 Sensor 1 Healthy [ =TRIB-EN02-B1R ]", "n1"),
        _mem("04_SPEED", "Safety Encoder 0001 Healthy [ =TRIB-EN02-B1R ]", "n1"),
        _mem("05_EM_STATE", "AREA 1 RESET", "AREA 1"),
        _mem("05_EM_STATE", "AREA 1 Q", "AREA 1"),
        _mem("05_EM_STATE", "SORTER_01_NOT_RUNNING", "0001"),
        _mem("02_COM", "AREA 1 E-STOP_PUSHBUTTONS", "AREA 1"),
        _mem("PROFINET_NODES_ALARM", "n0002-io 10.0.0.2", "pa1"),
        _mem("99_Commissioning", "n0002-io 10.0.0.2", "n0002-io", struct="NodesNotInstalled"),
    ]
    for role in ("STATE", "ALARM1", "ALARM2", "WARNING1", "WARNING2"):
        members.append(_mem("DiagnosticTags", f"S1.CABINET002.{role}", "2"))
        members.append(_mem("DiagnosticTags", f"S1.CABINET003.{role}", "3"))      # a cabinet without entries
    members += [_mem("DiagnosticTags", "S1.CABINET009.STATE", "9"), _mem("DiagnosticTags", "S1.CABINET009.ALARM1", "9")]
    entries = [_entry("e1", 2, 0, fl=NODE_BINDING, text="E-STOP =ES-0001"),
               _entry("kq1", 2, 33, fl='"PROFINET_NODES_ALARM"."n0099-gone 10.0.0.99"'),
               _entry("n1", 2, 20, source="logic"),
               _entry("pa1", 9, 1, text="FIELDBUS NODE FAILURE n0002-io"),
               _entry("f1", 2, 5, warning="true")]
    cabinets = [{"cabinet_id": "2", "index": "002", "fld": "=S1+SAFETY02", "template_type": "2"},
                {"cabinet_id": "3", "index": "003", "fld": "=S1+SAFETY03", "template_type": "1"},
                {"cabinet_id": "9", "index": "009", "fld": "=S1+SAFETY09", "template_type": "1"}]
    areas = [{"name": "AREA 1_TRIB", "number": "1001", "parent": "AREA 1", "part": "TRIB", "order": "2",
              "description": "", "sorter": "yes"},
             {"name": "AREA 1", "number": "1", "parent": "", "part": "", "order": "1", "description": "AREA 1",
              "sorter": ""}]
    interfaces = [{"instance": "SORTER-01", "description": "LOWER SORTER", "machine_type": "SORTER", "device": "-K1",
                   "is_diag": "false"}]
    elements = [{"interface": "SORTER-01", "signal_name": "PNC_Q_SORTER-01 HEARTBEAT", "description": "Blinking 1Hz",
                 "category": "WATCHDOG", "direction": "Q", "data_type": "BOOL", "io_address_side1": "Q10000.0"},
                {"interface": "SORTER-01", "signal_name": "", "description": "spare"}]
    return {"signals": signals, "db_members": members, "diagnosis_entries": entries, "diagnosis_cabinets": cabinets,
            "areas": areas, "interfaces": interfaces, "interface_elements": elements}


def _build(kinds=None, member_states=None, params=None, **kw):
    return model.build_plant(_database(), kinds or config.load_webui_kinds(),
                             member_states if member_states is not None else config.load_webui_member_states(),
                             params or config.load_webui_params(), diag=DIAG, tristate=set(), **kw)


def _types(findings):
    return {f.type: f for f in findings}


def test_exact_variable_names_and_the_poll_set():
    plant, _ = _build()
    eq(plant["poll"], [
        '"DiagnosticTags"."S1.CABINET002.STATE"', '"DiagnosticTags"."S1.CABINET002.ALARM1"',
        '"DiagnosticTags"."S1.CABINET002.ALARM2"', '"DiagnosticTags"."S1.CABINET002.WARNING1"',
        '"DiagnosticTags"."S1.CABINET002.WARNING2"',
        '"DiagnosticTags"."S1.CABINET009.STATE"', '"DiagnosticTags"."S1.CABINET009.ALARM1"',
        '"05_EM_STATE"."AREA 1 Q"', '"05_EM_STATE"."AREA 1 RESET"', '"02_COM"."AREA 1 E-STOP_PUSHBUTTONS"',
        '"05_EM_STATE"."SORTER_01_NOT_RUNNING"'],
        "the cabinets with entries (their words in STATE / alarm / warning order), then the areas' and sorters' "
        "members in rule order - no seed, no device member, no cabinet without an entry")
    node = plant["nodes"][0]
    eq([m["var"] for m in node["members"]],
       ['"PROFINET_NODES_ALARM"."n0002-io 10.0.0.2"', '"99_Commissioning"."NodesNotInstalled"."n0002-io 10.0.0.2"'],
       "a struct member is quoted level by level; a name with dots and spaces stays one quoted part")
    estop = next(d for d in plant["devices"] if d["kind"] == "estop")
    eq([t["var"] for t in estop["tags"]],
       ['"Emergency Push Button Lamp [ =ES-0001 ]"', '"Emergency Push Button [ =ES-0001 ]"'], "the PLC tags, quoted")
    cab2 = plant["cabinets"][0]
    eq((cab2["id"], cab2["index"], cab2["tristate"], [b["bit"] for b in cab2["bits"]]), (2, "002", True, [0, 5, 20, 33]),
       "template_type 2 = tristate; the bits in order")
    eq((cab2["bits"][0]["text"], cab2["bits"][0]["owner"], cab2["bits"][2]["source"]),
       ("E-STOP =ES-0001", "estop-0001", "logic"), "a bit names its text, its device, io or logic")


def test_family_and_index_grouping():
    plant, _ = _build()
    eq(sorted(d["id"] for d in plant["devices"]), ["contactor-0044", "encoder-0001", "estop-0001"],
       "one device per (kind, index): the lamp joins its e-stop, KQ1/2 + KQ2/2 + KI1/2 one contactor; a QBAD (no "
       "index) and a fire alarm (kind disabled) are no device; the Plc row no node")
    estop = next(d for d in plant["devices"] if d["id"] == "estop-0001")
    eq((estop["fld"], estop["functional_unit"], estop["device"], estop["description"]),
       ("=ES-0001", "=ES", "-0001", "EMERGENCY PUSH BUTTON PRESSED"), "the anchor E, not the lamp listed first")
    eq(estop["areas"], ["AREA 1", "AREA 1_TRIB"], "the areas in areas.csv order")
    contactor = next(d for d in plant["devices"] if d["id"] == "contactor-0044")
    eq((contactor["fld"], contactor["description"]), ("=TRIB-MA01-K50001", "FEEDBACK OF SAFETY RELAY FAULT"),
       "anchor KQ: KQ1/2 starts with it; the description falls back to a member signal's")
    eq(plant["counts"]["kinds"], {"estop": 1, "breaker": 0, "door": 0, "contactor": 1, "encoder": 1, "pn_node": 1})


def test_node_failed_resolution():
    plant, findings = _build()
    estop = next(d for d in plant["devices"] if d["id"] == "estop-0001")
    eq(estop["nodes"], ["pn_node-n0002-io"], "fl_value = the PA signal's plc_binding -> its node")
    eq(plant["nodes"][0]["diag"], [{"cabinet": 9, "bit": 1, "warning": False}], "a node's own diagnosis bit")
    eq(plant["cabinets"][1]["bits"][0]["owner"], "pn_node-n0002-io", "the node owns its cabinet bit")
    f = _types(findings).get("webui_node_unresolved")
    ok(f is not None and f.severity == "WARN" and "n0099-gone" in f.detail, "a binding naming no node is a WARN")
    contactor = next(d for d in plant["devices"] if d["id"] == "contactor-0044")
    eq(contactor["nodes"], [], "...and that device lists no node")


def test_a_further_kind_is_one_config_row():
    kinds = copy.deepcopy(config.load_webui_kinds())
    next(k for k in kinds if k["kind"] == "fire_alarm")["enabled"] = True
    plant, _ = _build(kinds=kinds)
    fire = [d for d in plant["devices"] if d["kind"] == "fire_alarm"]
    eq([(d["id"], d["fld"], d["diag"]) for d in fire], [("fire_alarm-0001", "=TRIC-FA01-B1",
                                                         [{"cabinet": 2, "bit": 5, "warning": True}])],
       "enabling the shipped fire_alarm row makes fire alarms devices - no code change")
    ok("fire_alarm" in [k["kind"] for k in plant["kinds"]], "and the page lists the kind")


def test_member_rules_and_polarity():
    plant, findings = _build()
    encoder = next(d for d in plant["devices"] if d["id"] == "encoder-0001")
    eq([(m["label"], m["role"]) for m in encoder["members"]],
       [("Encoder healthy", "state"), ("Sensor 1 healthy", "detail")],
       "the most specific rule wins ({n} would also match '0001 Sensor 1'), sorted by rule order")
    f = _types(findings).get("webui_polarity_unknown")
    ok(f is not None and f.severity == "INFO", "the shipped rules have no polarity yet: one INFO")
    rated = [dict(r, healthy=True) for r in config.load_webui_member_states()]
    _plant, findings = _build(member_states=rated)
    ok("webui_polarity_unknown" not in _types(findings), "every rule rated: no INFO")
    eq(_types(findings)["webui_cabinet_word_missing"].severity, "WARN", "cabinet 9 lacks three words")
    ok("S1.CABINET009.ALARM2" in _types(findings)["webui_cabinet_word_missing"].detail, "named")


def test_sorter_area_by_ordinal_and_interfaces():
    plant, _ = _build()
    eq([(s["id"], s["area"]) for s in plant["sorters"]], [("sorter-0001", "AREA 1_TRIB")])
    eq([(a["id"], a["sorter"], a["parent"]) for a in plant["areas"]],
       [("AREA 1", None, None), ("AREA 1_TRIB", "sorter-0001", "AREA 1")])
    eq([(i["id"], [e["var"] for e in i["elements"]]) for i in plant["interfaces"]],
       [("SORTER-01", ['"PNC_Q_SORTER-01 HEARTBEAT"'])], "an element without a signal name is not read")


def test_positions_stale_and_unplaced():
    positions = [{"kind": "estop", "fld": "=ES-0001", "x": 10.0, "y": 20.0},
                 {"kind": "door", "fld": "=GONE-01", "x": 1.0, "y": 2.0}]
    plant, findings = _build(positions=positions)
    eq(plant["layout"]["positions"]["estop|=ES-0001"], [10.0, 20.0])
    f = _types(findings)["webui_position_stale"]
    ok(f.severity == "WARN" and "door|=GONE-01" in f.detail, f.detail)
    ok("webui_unplaced" not in _types(findings), "no drawing: nothing to place")
    _plant, findings = _build(positions=positions, drawing={"file": "plant.svg", "width": 10, "height": 10,
                                                            "view_box": [0, 0, 10, 10]})
    ok("3 of 4" in _types(findings)["webui_unplaced"].detail, "with a drawing: the unplaced count")


def test_drawing_measure():
    with tempfile.TemporaryDirectory() as d:
        svg = os.path.join(d, "a.svg")
        open(svg, "w").write('<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 800">'
                             '</svg>')
        eq(project.measure(svg), {"width": 1200.0, "height": 800.0, "view_box": [0.0, 0.0, 1200.0, 800.0]})
        open(svg, "w").write('<svg width="300px" height="200"></svg>')
        eq(project.measure(svg)["view_box"], [0, 0, 300.0, 200.0])
        open(svg, "w").write('<svg></svg>')
        raises(ValueError, lambda: project.measure(svg))
        png = os.path.join(d, "a.png")
        open(png, "wb").write(b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", 640, 480))
        eq((project.measure(png)["width"], project.measure(png)["height"]), (640.0, 480.0))
        jpg = os.path.join(d, "a.jpg")
        open(jpg, "wb").write(b"\xff\xd8" + b"\xff\xe0" + struct.pack(">H", 4) + b"JF"
                              + b"\xff\xc0" + struct.pack(">HBHH", 11, 8, 300, 400) + b"\x03")
        eq((project.measure(jpg)["width"], project.measure(jpg)["height"]), (400.0, 300.0), "the SOF0 frame")


def test_template_bundle():
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "js", "views"))
        os.makedirs(os.path.join(d, "css"))
        open(os.path.join(d, "index.html"), "w").write("<html></html>")
        open(os.path.join(d, "README.md"), "w").write("notes")
        open(os.path.join(d, "js", "10_poller.js"), "w").write("var b = 2;\n")
        open(os.path.join(d, "js", "00_rpc.js"), "w").write("var a = 1;\n")
        open(os.path.join(d, "js", "views", "overview.js"), "w").write("var c = 3;\n")
        open(os.path.join(d, "css", "base.css"), "w").write("body{}\n")
        files = dict(project.bundle(d))
        eq(sorted(files), ["app.css", "app.js", "index.html"], "js/ and css/ joined, notes skipped")
        eq(files["app.js"].decode(), "// --- js/00_rpc.js ---\nvar a = 1;\n\n// --- js/10_poller.js ---\nvar b = 2;\n\n"
                                     "// --- js/views/overview.js ---\nvar c = 3;\n", "in path order, each named")
        open(os.path.join(d, "plant.json"), "w").write("{}")
        raises(ValueError, lambda: project.bundle(d))


def test_the_shipped_template_bundles():
    files = dict(project.bundle(config.WEBAPP_TEMPLATE_DIR))
    ok({"index.html", "app.js", "app.css"} <= set(files), sorted(files))
    text = b"".join(files.values()).decode("utf-8")
    ok("PlcProgram.Write" not in text, "the page never writes to the PLC")
    ok("http://" not in text.replace('xmlns="http://www.w3.org/2000/svg"', "") and "https://" not in text,
       "no external URL - the CPU serves everything")


if __name__ == "__main__":
    import sys
    sys.exit(run("webui_model", [
        ("exact_variable_names_and_the_poll_set", test_exact_variable_names_and_the_poll_set),
        ("family_and_index_grouping", test_family_and_index_grouping),
        ("node_failed_resolution", test_node_failed_resolution),
        ("a_further_kind_is_one_config_row", test_a_further_kind_is_one_config_row),
        ("member_rules_and_polarity", test_member_rules_and_polarity),
        ("sorter_area_by_ordinal_and_interfaces", test_sorter_area_by_ordinal_and_interfaces),
        ("positions_stale_and_unplaced", test_positions_stale_and_unplaced),
        ("drawing_measure", test_drawing_measure),
        ("template_bundle", test_template_bundle),
        ("the_shipped_template_bundles", test_the_shipped_template_bundles),
    ]))
