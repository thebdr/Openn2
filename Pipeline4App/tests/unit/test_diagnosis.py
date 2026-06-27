"""Phase 600a - the diagnosis config relocation + staging prereqs:
- config.load_signal_diagnosis (the relocated per-type diag attrs + the new `tristate` flag),
- config.load_diagnosis_columns (the DiagList column model, with the :03d/:02d format specs restored),
- identity.interp honoring a {token:spec} format spec (the diagnosis columns rely on it),
- the diagnosis_entries / diagnosis_cabinets table defs,
- staging.load_diagnosis_blocks (the DiagnosisBlocks-sheet -> diagnosis_cabinets port, over a synthetic xlsx).
"""
import os
import tempfile

from openpyxl import Workbook

from _harness import run, eq, ok
from pipeline4.core import config
from pipeline4.domain import identity, staging
from pipeline4.domain.diagnosis_entries import diagnosis_entries_table, diagnosis_cabinets_table


def test_interp_format_spec():
    eq(identity.interp("{diag_cabinet:03d}", {"diag_cabinet": "0"}), "000", "0 -> 000")
    eq(identity.interp("{diag_bit:02d}", {"diag_bit": "62"}), "62", "62 -> 62 (already 2 digits)")
    eq(identity.interp("{diag_cabinet:03d}", {"diag_cabinet": "5"}), "005")
    eq(identity.interp("{diag_cabinet:03d}", {"diag_cabinet": "1.0"}), "001", "a float-read int coerces")
    eq(identity.interp("{diag_cabinet:03d}", {"diag_cabinet": ""}), "", "a blank value is NOT padded")
    eq(identity.interp("[ {x} {y} ]", {"x": "A", "y": "B"}), "[ A B ]", "bare tokens unchanged")
    eq(identity.interp("{name}", {"name": "x"}), "x", "no spec -> verbatim")


def test_load_signal_diagnosis():
    d = config.load_signal_diagnosis()
    ok("E1/2".upper() in d and "PA" in d, "the in_diag types are present")
    eq(d["E1/2"]["in_diag"], True)
    eq(d["E1/2"]["diag_logic"], "invert")
    eq(d["E1/2"]["tristate"], True, "E1/2 is the tristate type")
    eq(d["E1/2"]["tristate_desc"], "EMERGENCY PUSH-BUTTON RELEASED {combined_FLD}")
    eq(d["PA"]["diag_logic"], "mirror")
    eq(d["PA"]["diag_desc"], "FIELDBUS NODE FAILURE {profinet_name} {profinet_ip}")
    eq(d["B1/2"]["tristate"], False, "a non-tristate in_diag type")
    ok("Z#" in d and d["Z#"]["in_diag"] is True, "a pattern type carries its diag attrs (keyed by type_id)")


def test_load_diagnosis_columns():
    cols = config.load_diagnosis_columns()
    headers = [c["header"] for c in cols]
    eq(headers[0], "Diag Cabinet")
    eq(cols[0]["expression"], "{diag_cabinet:03d}", "the :03d spec is restored")
    eq(cols[1]["expression"], "{diag_bit:02d}", "the :02d spec is restored")
    ok(any(c["expression"].strip() == "$PLC_Binding$" for c in cols), "the PLC_Binding sentinel column")
    eq(len(cols), 19, "the 19 DiagList columns")


def test_table_defs():
    e = diagnosis_entries_table()
    eq(e.name, "diagnosis_entries")
    for c in ("source", "cabinet", "bit", "is_warning", "in_binding", "ml_value", "fl_value", "diag_columns"):
        ok(c in e.columns, f"{c} column present")
    ok("is_warning" in e.json_columns and "diag_columns" in e.json_columns, "the JSON cells")
    c = diagnosis_cabinets_table()
    eq(c.name, "diagnosis_cabinets")
    for col in ("cabinet_id", "index", "fld", "template_type", "swp"):
        ok(col in c.columns, f"{col} column present")
    eq(c.key_columns, ["cabinet_id"])


def _diagblocks_xlsx(path, rows, sheet="DiagnosisBlocks"):
    wb = Workbook()
    ws = wb.active
    ws.title = sheet
    ws.append(["ID_Local", "ID_SWP", "Functional Unit", "Location", "FullName", "TemplateType"])
    for r in rows:
        ws.append(r)
        rr = ws.max_row
        for c, v in enumerate(r, 1):                      # the real sheet stores FU/FullName as TEXT;
            if isinstance(v, str) and v[:1] in ("=", "+", "-"):   # force it (else openpyxl = a formula,
                ws.cell(rr, c).data_type = "s"                    # which a data_only read returns as None)
    wb.save(path)


def test_load_diagnosis_blocks():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "iol.xlsx")
        _diagblocks_xlsx(p, [
            [0, 0, "=S1", "+MC1", "=S1+MC1.CC1", "1"],
            [2, 5, "=S1", "+IN1", "=S1+IN1.CC1", "2"],     # ID_SWP differs from ID_Local
            ["", "", "", "", "orphan", ""],                # non-numeric key -> skipped
        ])
        cabs = staging.load_diagnosis_blocks(p)
        eq(set(cabs), {0, 2}, "keyed by ID_Local (int), the non-numeric row skipped")
        eq(cabs[0], {"index": "000", "fld": "=S1+MC1.CC1", "template_type": "1", "swp": "0"})
        eq(cabs[2]["template_type"], "2", "TemplateType -> the SCL 01-04 variant")
        eq(cabs[2]["swp"], "5", "ID_SWP kept when it differs from ID_Local")


def test_load_diagnosis_blocks_absent():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "no_sheet.xlsx")
        wb = Workbook(); wb.active.title = "NET SAFETY 50"; wb.active["A1"] = "x"; wb.save(p)
        eq(staging.load_diagnosis_blocks(p), {}, "no DiagnosisBlocks sheet -> {}")
        eq(staging.load_diagnosis_blocks(""), {}, "no path -> {}")


# =================================================================================================== #
# Phase 600b - the builder (io_entries + the OR/per-row logic rules + ml/fl/node -> diagnosis_entries)
# =================================================================================================== #
from pipeline4.core.database import Database
from pipeline4.domain import diagnosis
from pipeline4.domain.signals import signals_table


def test_ml_value():
    eq(diagnosis.ml_value({"type": {"diag_logic": "mirror"}}), "TRUE", "mirror -> TRUE")
    eq(diagnosis.ml_value({"type": {"diag_logic": "invert"}}), "FALSE", "invert -> FALSE")
    eq(diagnosis.ml_value({"type": {}, "normal_condition": "1"}), "FALSE", "blank + a set normal_condition -> FALSE")
    eq(diagnosis.ml_value({"type": {}, "normal_condition": ""}), "TRUE", "blank + empty -> TRUE")


def test_node_of_and_fl_value():
    node = {"profinet_name": "n10", "profinet_ip": "192.168.50.10", "bit": "I10.0",
            "I_startByte": 10, "I_endByte": 12, "Q_startByte": "", "Q_endByte": ""}
    inside = {"bit": "I11.3"}     # byte 11 in [10,12]
    outside = {"bit": "I20.0"}
    rows = [node, inside, outside]
    eq(diagnosis.node_of(rows, inside), node, "an in-range signal resolves to the node")
    ok(diagnosis.node_of(rows, outside) is None, "out-of-range -> no node")
    eq(diagnosis.fl_value(rows, inside), '"PROFINET_NODES_ALARM"."n10 192.168.50.10"', "FL = the node alarm")
    eq(diagnosis.fl_value(rows, node), "false", "a node never self-filters")
    eq(diagnosis.fl_value(rows, outside), "false", "no node -> false")


def _sig(**kw):
    row = {"type": {}, "type_hw": "", "diag_cabinet": "", "diag_bit": "", "functional_unit": "",
           "location": "", "device": "", "script_type": "", "plc_binding": ""}
    row.update(kw)
    return row


def test_resolve_logic_or_next_free_bit_and_cabinet():
    rules = [{"name": "Enc", "required_types": ["N1/2", "N2/2"], "dev_type": "A",
              "db_name": "04_SPEED", "member": "M {index}", "diag_desc": ""}]
    rows = [
        # an in-diag alarm already at (cabinet 2, bit 0) -> seeds `used`
        _sig(type={"in_diag": True}, type_hw="A", diag_cabinet="2", diag_bit="0"),
        _sig(script_type="N1/2", diag_cabinet="2", index="01"),               # numeric cabinet -> 2, next bit 1
        _sig(script_type="N2/2", functional_unit="=S1", location="+M1", device="-N",  # no cabinet; sibling FLD
             index="02"),
        _sig(script_type="DD"),                                               # not in required_types -> no match
    ]
    # a sibling sharing the N2/2 row's FLD that DOES carry a numeric cabinet (paired-channel co-location)
    rows.append(_sig(type={"in_diag": True}, type_hw="A", functional_unit="=S1", location="+M1",
                     device="-N", diag_cabinet="7", diag_bit="3"))
    items = diagnosis.resolve_logic(rows, cabinets=[], rules=rules)
    eq(len(items), 2, "OR fires once per matching N1/2 + N2/2 row; DD no-match")
    by_st = {it["src"]["script_type"]: it for it in items}
    eq((by_st["N1/2"]["cabinet"], by_st["N1/2"]["bit"]), (2, 1), "numeric cabinet 2, next free alarm bit (0 taken)")
    eq(by_st["N2/2"]["cabinet"], 7, "no own cabinet -> the paired-channel sibling's (FLD =S1+M1-N -> 7)")
    eq(by_st["N1/2"]["binding"], '"04_SPEED"."M 01"', "binding = db.member (member template resolved)")


def test_resolve_logic_cabinet_from_blocks():
    rules = [{"name": "Enc", "required_types": ["N1/2"], "dev_type": "A", "db_name": "04_SPEED",
              "member": "M", "diag_desc": ""}]
    rows = [_sig(script_type="N1/2", functional_unit="=S1", location="+Z1", device="-N")]  # no cabinet, no sibling
    cabinets = [{"cabinet_id": "9", "fld": "=S1+Z1"}]      # FU+LOC matches the DiagnosisBlocks FullName
    items = diagnosis.resolve_logic(rows, cabinets, rules)
    eq(len(items), 1)
    eq(items[0]["cabinet"], 9, "FU+LOC -> the diagnosis_cabinets FLD lookup")


def test_build_unified_io_and_logic():
    cols = signals_table(["functional_unit", "location", "device", "script_type", "bit",
                          "diag_cabinet", "diag_bit", "type_hw", "index", "desc_l1", "combined_FLD", "iol_FLD"])
    db = Database([cols, diagnosis_cabinets_table()])
    db["signals"].add(script_type="A", type={"in_diag": True, "diag_logic": ""}, type_hw="A",
                      diag_cabinet="1", diag_bit="5", bit="I1.0", desc_l1="ALARM",
                      plc_binding='"Alarms_Warnings"."x"')
    db["signals"].add(script_type="N1/2", type={"in_diag": True, "diag_logic": "invert"}, type_hw="N",
                      diag_cabinet="2", diag_bit="0", index="01", functional_unit="=S1", location="+M1",
                      combined_FLD="=S1+M1", iol_FLD="=S1+M1", plc_binding='"04_SPEED"."enc"')
    db, errors, _w = diagnosis.build(db)
    eq(errors, [])
    entries = list(db["diagnosis_entries"])
    io = [e for e in entries if e["source"] == "io"]
    logic = [e for e in entries if e["source"] == "logic"]
    eq(len(io), 2, "both in_diag signals -> io entries")
    eq(len(logic), 1, "the Safety Encoder rule fires on the N1/2 row")
    le = logic[0]
    eq((le["rule_name"], int(le["cabinet"]), int(le["bit"])), ("Safety Encoder Failure", 2, 1),
       "logic entry: cabinet 2 (the N1/2 cabinet), next free alarm bit 1 (0 taken by the io seed)")
    a_io = next(e for e in io if e["source_signal"] and e["diag_columns"].get("DevType") == "A")
    eq(a_io["diag_columns"]["Diag Cabinet"], "001", "the :03d format spec padded the Diag Cabinet cell")
    eq(le["diag_columns"]["Diag Desc"], "SAFETY ENCODER FAILURE =S1+M1", "the rule diag_desc names the logic row")


# =================================================================================================== #
# Phase 600c - the DiagList CSV projections (filter diagnosis_entries by source -> the two CSVs)
# =================================================================================================== #
import csv

from pipeline4.domain import diaglist_csv


def _built_db():
    cols = signals_table(["functional_unit", "location", "device", "script_type", "bit",
                          "diag_cabinet", "diag_bit", "type_hw", "index", "desc_l1", "combined_FLD", "iol_FLD"])
    db = Database([cols, diagnosis_cabinets_table()])
    db["signals"].add(script_type="A", type={"in_diag": True}, type_hw="A", diag_cabinet="1", diag_bit="5",
                      bit="I1.0", desc_l1="ALARM", plc_binding='"Alarms_Warnings"."x"')
    db["signals"].add(script_type="N1/2", type={"in_diag": True, "diag_logic": "invert"}, type_hw="N",
                      diag_cabinet="2", diag_bit="0", index="01", functional_unit="=S1", location="+M1",
                      combined_FLD="=S1+M1", iol_FLD="=S1+M1", plc_binding='"04_SPEED"."enc"')
    db, _e, _w = diagnosis.build(db)
    return db


def test_diaglist_project():
    db = _built_db()
    with tempfile.TemporaryDirectory() as d:
        res = diaglist_csv.project(db, out_dir=d)
        eq((res["io_count"], res["logic_count"]), (2, 1), "io -> IO.csv, logic -> Logic.csv")
        headers = [c["header"] for c in config.load_diagnosis_columns()]
        with open(res["io_path"], newline="", encoding="utf-8") as fh:
            io = list(csv.reader(fh))
        eq(io[0], headers, "DiagList_IO header = the config columns in order")
        eq(len(io), 3, "header + 2 io rows")
        cab_i = headers.index("Diag Cabinet")
        ok("001" in [r[cab_i] for r in io[1:]], "a padded Diag Cabinet (:03d) is present")
        with open(res["logic_path"], newline="", encoding="utf-8") as fh:
            logic = list(csv.reader(fh))
        eq(len(logic), 2, "header + 1 logic row")
        pb = headers.index("PLC_Binding")
        eq(logic[1][pb], '"04_SPEED"."Safety Encoder 01 Healthy [ =S1+M1 ]"', "the rule binding in PLC_Binding")


def test_diaglist_crlf_no_bom():
    db = _built_db()
    with tempfile.TemporaryDirectory() as d:
        res = diaglist_csv.project(db, out_dir=d)
        raw = open(res["io_path"], "rb").read()
        ok(b"\r\n" in raw, "CRLF line endings (matches the reference)")
        ok(raw[:3] != b"\xef\xbb\xbf", "no BOM")


# =================================================================================================== #
# Phase 600d - the OPC SCL projection (render_scl + tristate from template_type OR a per-type signal)
# =================================================================================================== #
from pipeline4.domain import diagnosis_scl

_SCL_TEMPLATE = (
    'FUNCTION "TEMPLATE--v1.0--06_Diagnostic for OPC" : Void\n'
    "BEGIN\n"
    "\tREGION !!NetworkComment$$\n"
    '\t    "!!instanceOf-CabState$$"(STATE := "DiagnosticTags"."S1.CABINET!!cabinetIndex$$.STATE");\n'
    "\t    // #Template 01 : NoTristate\n"
    '\t    "!!instanceOf-BoolToUDInt$$"(IN_00 := false,\n'
    "\t                                ML_00 := TRUE,\n"
    "\t                                FL_00 := false,\n"
    '\t                                Alarm_Warning_DW := "DiagnosticTags"."S1.CABINET!!cabinetIndex$$.!!Alarm_Warning_DW$$");\n'
    "\t    // #Template End\n"
    "\t    // #Template 02 : Tristate\n"
    '\t    "!!instanceOf-BoolToUDInt$$"(IN_00 := false,\n'
    "\t                                ML_00 := TRUE,\n"
    "\t                                FL_00 := false,\n"
    '\t                                Alarm_DW := "DiagnosticTags"."S1.CABINET!!cabinetIndex$$.!!Alarm_DW$$",\n'
    '\t                                Tristate_DW := "DiagnosticTags"."S1.CABINET!!cabinetIndex$$.!!Warning_DW$$");\n'
    "\t    // #Template End\n"
    "\tEND_REGION\n"
    "END_FUNCTION\n"
)


def _entry(cabinet, bit, is_warning, in_="x", ml="TRUE", fl="false"):
    return {"cabinet": cabinet, "bit": bit, "is_warning": is_warning, "in": in_, "ml": ml, "fl": fl}


def test_render_scl_variants_and_rename():
    blocks = {1: {"index": "001", "template_type": "1", "fld": "=S1+C1"},
              2: {"index": "002", "template_type": "2", "fld": "=S1+C2"}}
    entries = [_entry(1, 0, False, in_='"DB"."a1"'),                 # cab1 tt=1 -> non-tristate
               _entry(2, 0, False, in_='"DB"."a2"'), _entry(2, 0, True, in_='"DB"."w2"')]  # cab2 tt=2 -> tristate
    out = diagnosis_scl.render_scl(blocks, entries, _SCL_TEMPLATE)
    ok('FUNCTION "06_Diagnostic for OPC"' in out, "FUNCTION renamed (TEMPLATE--vX.Y-- dropped)")
    ok("REGION =S1+C1" in out and "REGION =S1+C2" in out, "one REGION per cabinet, NetworkComment = fld")
    ok('"S1.CABINET001.STATE"' in out, "the CabState instance per cabinet")
    ok('IN_00 := "DB"."a1"' in out, "the channel IN binding is plugged")
    # cab1 non-tristate: an Alarm_Warning_DW call, no Tristate_DW
    ok("S1.CABINET001.ALARM1" in out and "CABINET001" in out, "cab1 alarm DWord")
    c1 = out[out.index("REGION =S1+C1"):out.index("REGION =S1+C2")]
    ok("Tristate_DW" not in c1, "cab1 (tt=1) is NOT tristate")
    # cab2 tristate: alarm paired with warning (Tristate_DW present)
    c2 = out[out.index("REGION =S1+C2"):]
    ok("Tristate_DW" in c2 and "S1.CABINET002.WARNING1" in c2, "cab2 (tt=2) pairs alarm+warning (tristate)")


def test_render_scl_per_type_tristate_trigger():
    blocks = {1: {"index": "001", "template_type": "1", "fld": "C1"}}    # template_type=1 (non-tristate)
    entries = [_entry(1, 0, False), _entry(1, 0, True)]
    plain = diagnosis_scl.render_scl(blocks, entries, _SCL_TEMPLATE)
    ok("Tristate_DW" not in plain, "tt=1 + no per-type trigger -> non-tristate")
    triggered = diagnosis_scl.render_scl(blocks, entries, _SCL_TEMPLATE, tristate_cabinets={1})
    ok("Tristate_DW" in triggered, "the per-type tristate flag forces tristate even on a tt=1 cabinet")


def test_scl_project_writes_bom_crlf():
    db = _built_db()                                          # has diagnosis_entries (cab 1 + cab 2)
    db["diagnosis_cabinets"].add(cabinet_id=2, index="002", fld="=S1+M1", template_type="2", swp="2")
    with tempfile.TemporaryDirectory() as d:
        res = diagnosis_scl.project(db, out_dir=d, template_path=None)  # real template (DIAG_SCL_TEMPLATE)
        if res["path"] is None:                              # template absent in this checkout -> skip the file asserts
            ok(res["warnings"], "a missing template degrades to a warning, no crash"); return
        raw = open(res["path"], "rb").read()
        ok(raw[:3] == b"\xef\xbb\xbf", "UTF-8 BOM")
        ok(b"\r\n" in raw, "CRLF")
        ok(res["entries"] >= 2 and res["cabinets"] >= 1, "entries + cabinets reported")


def test_scl_project_synthetic_template():
    db = _built_db()
    db["diagnosis_cabinets"].add(cabinet_id=2, index="002", fld="=S1+M1", template_type="2", swp="2")
    with tempfile.TemporaryDirectory() as d:
        tpl = os.path.join(d, "scl.scl")
        open(tpl, "w", encoding="utf-8").write(_SCL_TEMPLATE)
        res = diagnosis_scl.project(db, out_dir=d, template_path=tpl)
        text = open(res["path"], encoding="utf-8-sig").read()
        ok('FUNCTION "06_Diagnostic for OPC"' in text, "rename applied end-to-end")
        ok("Tristate_DW" in text, "the tt=2 cabinet 2 renders tristate")


if __name__ == "__main__":
    import sys
    sys.exit(run("diagnosis", [
        ("interp_format_spec", test_interp_format_spec),
        ("load_signal_diagnosis", test_load_signal_diagnosis),
        ("load_diagnosis_columns", test_load_diagnosis_columns),
        ("table_defs", test_table_defs),
        ("load_diagnosis_blocks", test_load_diagnosis_blocks),
        ("load_diagnosis_blocks_absent", test_load_diagnosis_blocks_absent),
        ("ml_value", test_ml_value),
        ("node_of_and_fl_value", test_node_of_and_fl_value),
        ("resolve_logic_or_next_free_bit_and_cabinet", test_resolve_logic_or_next_free_bit_and_cabinet),
        ("resolve_logic_cabinet_from_blocks", test_resolve_logic_cabinet_from_blocks),
        ("build_unified_io_and_logic", test_build_unified_io_and_logic),
        ("diaglist_project", test_diaglist_project),
        ("diaglist_crlf_no_bom", test_diaglist_crlf_no_bom),
        ("render_scl_variants_and_rename", test_render_scl_variants_and_rename),
        ("render_scl_per_type_tristate_trigger", test_render_scl_per_type_tristate_trigger),
        ("scl_project_writes_bom_crlf", test_scl_project_writes_bom_crlf),
        ("scl_project_synthetic_template", test_scl_project_synthetic_template),
    ]))
