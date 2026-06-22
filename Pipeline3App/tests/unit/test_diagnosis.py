"""M8 gate (data-independent): Phase 600 / 610 Generate Diag List.

build_diag_list_io (in-diagnosis rows -> the config-driven columns + the $PLC_Binding$ sentinel),
build_diag_list_logic (rule-generated rows: ALL required_types per cabinet -> next free bit), the
CSV write, and the phase wiring. 620 (the OPC SCL) is tested when built.
"""
import os
import tempfile
from _harness import run, eq, ok

from pipeline3.core import config
from pipeline3.context import PipelineContext
from pipeline3.domain import diagnosis
from pipeline3.io import csv_tables
import pipeline3.phases  # registers all phases
from pipeline3.phases import p600_diagnosis
from pipeline3.registry import registry


def _row(in_diag=True, script_type="A", diag_cabinet="001", diag_bit="05", type_hw="A",
         name_in_db="", datablocks="", name_in_tagtable="", fu="=S1", loc="+MS1", dev="-K1", **extra):
    r = {"_type": {"in_diagnosis": in_diag}, "script_type": script_type,
         "diag_cabinet": diag_cabinet, "diag_bit": diag_bit, "type_hw": type_hw,
         "functional_unit": fu, "location": loc, "device": dev,
         "name_in_db": name_in_db, "datablocks": datablocks, "name_in_tagtable": name_in_tagtable}
    r.update(extra)
    return r


_DOOR_RULE = [{"name": "Door Alarm", "required_types": ["DI1/2", "DI2/2"], "dev_type": "A",
               "db_name": "07_DOOR", "member": "Door Alarm [ {functional_unit}{location}{device} ]"}]


# --- 610a: DiagList_IO ---------------------------------------------------------------------- #

def test_build_diag_list_io():
    rows = [_row(in_diag=True, diag_cabinet="001", diag_bit="05", name_in_db="Alarm X", datablocks="01_PB"),
            _row(in_diag=False, name_in_db="Y", datablocks="01_PB")]
    io = diagnosis.build_diag_list_io(rows)
    eq(len(io), 1, "only in-diagnosis rows")
    r0 = io[0]
    ok("Diag Cabinet" in r0 and "PLC_Binding" in r0, "config-driven columns present")
    eq(r0["Diag Cabinet"], "001"); eq(r0["Diag Bit"], "05")
    eq(r0["PLC_Binding"], '"01_PB"."Alarm X"', "$PLC_Binding$ sentinel -> identity.plc_binding")
    eq(r0["Functional unit"], "=S1")


def test_diag_io_tag_binding():
    # no db member -> binding falls back to the tag
    io = diagnosis.build_diag_list_io([_row(in_diag=True, name_in_db="", name_in_tagtable="MyTag")])
    eq(io[0]["PLC_Binding"], '"MyTag"')


# --- 610b: DiagList_Logic (rule-generated) ------------------------------------------------- #

def test_logic_or_per_row():
    # pipe = OR + fire per matching row: DI1/2 and DI2/2 each match DI1/2|DI2/2 -> two entries; DD not
    rows = [
        _row(in_diag=True, script_type="DI1/2", diag_cabinet="002", diag_bit="00",
             type_hw="A", fu="=S1", loc="+SG1", dev="-B1"),
        _row(in_diag=True, script_type="DI2/2", diag_cabinet="002", diag_bit="01",
             type_hw="A", fu="=S1", loc="+SG2", dev="-B2"),
        _row(in_diag=True, script_type="DD", diag_cabinet="002", diag_bit="02",
             type_hw="A", fu="=S1", loc="+SG3", dev="-B3"),
    ]
    logic = diagnosis.build_diag_list_logic(rows, {}, rules=_DOOR_RULE)
    eq(len(logic), 2, "one entry per matching row (DI1/2, DI2/2); DD excluded")
    eq([l["DevType"] for l in logic], ["Door Alarm", "Door Alarm"], "DevType = the rule name")
    eq([l["Type"] for l in logic], ["A", "A"], "Type = the rule dev_type")
    eq({l["PLC_Binding"] for l in logic},
       {'"07_DOOR"."Door Alarm [ =S1+SG1-B1 ]"', '"07_DOOR"."Door Alarm [ =S1+SG2-B2 ]"'})


def test_logic_fires_on_any():
    # OR: a lone DI1/2 fires (it does NOT require DI2/2 to also be present)
    rows = [_row(in_diag=True, script_type="DI1/2", diag_cabinet="002", diag_bit="00",
                 type_hw="A", fu="=S1", loc="+SG1", dev="-B1")]
    eq(len(diagnosis.build_diag_list_logic(rows, {}, rules=_DOOR_RULE)), 1)


def test_logic_next_free_bit():
    rule = [{"name": "Alm", "required_types": ["A"], "dev_type": "A", "db_name": "DB",
             "member": "M [ {functional_unit}{location}{device} ]"}]
    rows = [_row(in_diag=True, script_type="ZZ", diag_cabinet="002", diag_bit="00", type_hw="A", dev="-Z1"),
            _row(in_diag=True, script_type="A", diag_cabinet="002", diag_bit="05", type_hw="A", dev="-A1")]
    logic = diagnosis.build_diag_list_logic(rows, {}, rules=rule)
    eq(len(logic), 1); eq(logic[0]["Diag Cabinet"], "002")
    eq(logic[0]["Diag Bit"], "01", "alarm bits 0 (ZZ) and 5 (A) used -> next free is 1")


def test_logic_paired_channel_sibling():
    # a rule matching the diagnosis channel DI2/2 (in_diag=no, no cabinet) co-locates it with its
    # DI1/2 sibling (same device FLD, carries the cabinet)
    rule = [{"name": "Door", "required_types": ["DI2/2"], "dev_type": "A", "db_name": "07_DOOR",
             "member": "Door Alarm [ {functional_unit}{location}{device} ]"}]
    rows = [_row(in_diag=True, script_type="DI1/2", diag_cabinet="010", diag_bit="01", type_hw="A",
                 fu="=S1", loc="+SG1", dev="-B1"),
            _row(in_diag=False, script_type="DI2/2", diag_cabinet="", diag_bit="", type_hw="A",
                 fu="=S1", loc="+SG1", dev="-B1")]
    logic = diagnosis.build_diag_list_logic(rows, {}, rules=rule)
    eq(len(logic), 1, "DI2/2 matches; co-locates to its sibling's cabinet 010")
    eq(logic[0]["Diag Cabinet"], "010"); eq(logic[0]["Diag Bit"], "00")
    eq(logic[0]["PLC_Binding"], '"07_DOOR"."Door Alarm [ =S1+SG1-B1 ]"')


def test_logic_fld_fallback_cabinet():
    # a matched row with no diag_cabinet AND no sibling resolves via FLD -> DiagnosisBlocks
    rule = [{"name": "Enc", "required_types": ["N1/2"], "dev_type": "A", "db_name": "04_SPEED",
             "member": "Enc [ {functional_unit}{location} ]"}]
    rows = [_row(in_diag=True, script_type="N1/2", diag_cabinet="", diag_bit="", fu="=S1", loc="+PC1", dev="-X1")]
    blocks = {7: {"index": "007", "fld": "=S1+PC1", "template_type": "1", "swp": "7"}}
    logic = diagnosis.build_diag_list_logic(rows, blocks, rules=rule)
    eq(len(logic), 1); eq(logic[0]["Diag Cabinet"], "007", "cabinet from FLD->DiagnosisBlocks")


def test_logic_diag_desc_rule_override_and_fallback():
    # a rule-supplied diag_desc names the rule-generated diagnosis (e.g. "SAFETY ENCODER FAILURE
    # <FLD>"); a rule WITHOUT one (or with a blank) keeps the source signal's own diag_desc.
    base = {"name": "Enc", "required_types": ["N1/2"], "dev_type": "A", "db_name": "04_SPEED",
            "member": "Safety Encoder Healthy [ {functional_unit}{location}{device} ]"}
    row = _row(in_diag=True, script_type="N1/2", diag_cabinet="011", diag_bit="00", type_hw="A",
               fu="=S1", loc="+PC1", dev="-X1", diag_desc="SOURCE ENCODER DESC")
    with_desc = [{**base, "diag_desc": "SAFETY ENCODER FAILURE {functional_unit}{location}{device}"}]
    a = diagnosis.build_diag_list_logic([row], {}, rules=with_desc)
    eq(a[0]["Diag Desc"], "SAFETY ENCODER FAILURE =S1+PC1-X1", "rule diag_desc drives the Diag Desc")
    eq(a[0]["PLC_Binding"], '"04_SPEED"."Safety Encoder Healthy [ =S1+PC1-X1 ]"')
    b = diagnosis.build_diag_list_logic([row], {}, rules=[base])              # no diag_desc key
    eq(b[0]["Diag Desc"], "SOURCE ENCODER DESC", "no rule diag_desc -> keep the source signal's")
    c = diagnosis.build_diag_list_logic([row], {}, rules=[{**base, "diag_desc": ""}])  # blank
    eq(c[0]["Diag Desc"], "SOURCE ENCODER DESC", "blank rule diag_desc -> keep the source signal's")


def test_logic_warning_family():
    # the warning family (dev_type ends 'W') is independent of the alarm family in a cabinet
    rule = [{"name": "Warn", "required_types": ["A"], "dev_type": "AW", "db_name": "DB", "member": "M{device}"}]
    rows = [_row(in_diag=True, script_type="ALM", diag_cabinet="003", diag_bit="00", type_hw="A", dev="-X1"),
            _row(in_diag=True, script_type="A", diag_cabinet="003", diag_bit="00", type_hw="AW", dev="-A1")]
    logic = diagnosis.build_diag_list_logic(rows, {}, rules=rule)
    eq(len(logic), 1); eq(logic[0]["Type"], "AW", "dev_type ending W -> warning family")
    eq(logic[0]["Diag Bit"], "01", "warning bit 0 taken by the AW in-diag row -> next free 1")


# --- 620: the OPC diagnosis SCL ------------------------------------------------------------ #

_SCL_TPL = '''FUNCTION "TEMPLATE--v1.0--06_Diagnostic for OPC" : Void
{ S7_Optimized_Access := 'TRUE' }
VERSION : 0.1

BEGIN
    REGION !!NetworkComment$$
        "!!instanceOf-CabState$$"(ALARM1 := "DiagnosticTags"."S1.CABINET!!cabinetIndex$$.ALARM1",
                                  STATE := "DiagnosticTags"."S1.CABINET!!cabinetIndex$$.STATE");

        // #Template 01 : AutoReset, NoTristate
        "!!instanceOf-BoolToUDInt$$"(IN_00 := false,
                                     ML_00 := TRUE,
                                     FL_00 := false,
                                     Alarm_Warning_DW := "DiagnosticTags"."S1.CABINET!!cabinetIndex$$.!!Alarm_Warning_DW$$"
        );
        // #Template End

        // #Template 02 : AutoReset, Tristate
        "!!instanceOf-BoolToUDInt$$"(IN_00 := false,
                                     ML_00 := TRUE,
                                     FL_00 := false,
                                     Alarm_Warning_DW := "DiagnosticTags"."S1.CABINET!!cabinetIndex$$.!!Alarm_DW$$",
                                     Tristate_DW => "DiagnosticTags"."S1.CABINET!!cabinetIndex$$.!!Warning_DW$$"
        );
        // #Template End

END_REGION
END_FUNCTION
'''


def test_ml_value():
    eq(diagnosis.ml_value({"_type": {"diagnosis_logic": "mirror"}}), "TRUE")
    eq(diagnosis.ml_value({"_type": {"diagnosis_logic": "invert"}}), "FALSE")
    eq(diagnosis.ml_value({"_type": {}, "normal_condition": "1"}), "FALSE", "normal_condition set -> FALSE")
    eq(diagnosis.ml_value({"_type": {}, "normal_condition": ""}), "TRUE")


def test_node_of_and_fl_value():
    node = {"profinet_name": "n1", "profinet_ip": "1.1.1.1",
            "I_startByte": 0, "I_endByte": 5, "Q_startByte": "", "Q_endByte": ""}
    sig = {"bit": "I3.0"}
    rows = [node, sig]
    eq(diagnosis.node_of(rows, sig), node, "signal at I3 falls in the node's I0..5 range")
    eq(diagnosis.fl_value(rows, sig), '"PROFINET_NODES_ALARM"."n1 1.1.1.1"')
    eq(diagnosis.fl_value(rows, node), "false", "the node-down alarm itself does not self-filter")
    eq(diagnosis.fl_value(rows, {"bit": "I9.0"}), "false", "no node range contains I9")


def test_render_scl():
    entries = [
        {"cabinet": 1, "bit": 0, "is_warning": False, "in": '"DB"."A"', "ml": "TRUE", "fl": "false"},
        {"cabinet": 1, "bit": 1, "is_warning": False, "in": '"DB"."B"', "ml": "FALSE",
         "fl": '"PROFINET_NODES_ALARM"."n1 1.1.1.1"'},
    ]
    blocks = {1: {"index": "001", "fld": "=S1+C1", "template_type": "1"}}
    scl = diagnosis.render_scl(blocks, entries, _SCL_TPL)
    ok("REGION =S1+C1" in scl, "NetworkComment = the cabinet FLD")
    ok('"S1.CABINET001.STATE"(' in scl, "CabState instance")
    ok('"S1.CABINET001.ALARM1"(' in scl, "ALARM1 DWord instance")
    ok('IN_00 := "DB"."A",' in scl and 'IN_01 := "DB"."B",' in scl, "channels placed by bit")
    ok("ML_01 := FALSE," in scl)
    ok('FL_01 := "PROFINET_NODES_ALARM"."n1 1.1.1.1",' in scl)
    ok('Alarm_Warning_DW := "DiagnosticTags"."S1.CABINET001.ALARM1"' in scl, "tail DWord bound")
    ok('FUNCTION "06_Diagnostic for OPC"' in scl, "FUNCTION renamed (TEMPLATE--vX.Y-- prefix dropped)")
    ok("TEMPLATE--v" not in scl, "no template prefix remains")
    ok(scl.rstrip().endswith("END_FUNCTION"), "well-formed tail")


def test_render_scl_tristate_and_warning_split():
    # tt=2 (tristate): an alarm DWord pairs its warning DWord (Alarm_DW + Tristate_DW)
    entries = [{"cabinet": 2, "bit": 0, "is_warning": False, "in": "X", "ml": "TRUE", "fl": "false"}]
    blocks = {2: {"index": "002", "fld": "=S2+C2", "template_type": "2"}}
    scl = diagnosis.render_scl(blocks, entries, _SCL_TPL)
    ok('Alarm_Warning_DW := "DiagnosticTags"."S1.CABINET002.ALARM1"' in scl, "tristate alarm DWord")
    ok('Tristate_DW => "DiagnosticTags"."S1.CABINET002.WARNING1"' in scl, "tristate pairs the warning DWord")


def test_generate_diag_scl():
    with tempfile.TemporaryDirectory() as d:
        tpl = os.path.join(d, "tpl.scl")
        with open(tpl, "w", encoding="utf-8") as f:
            f.write(_SCL_TPL)
        rows = [_row(in_diag=True, script_type="A", diag_cabinet="001", diag_bit="00", type_hw="A",
                     name_in_db="A", datablocks="DB")]
        res = diagnosis.generate_diag_scl(rows, d, io_path=None, template_path=tpl)
        eq(res["entries"], 1); eq(res["cabinets"], 1); eq(res["warnings"], [])
        ok(res["path"].endswith("Diagnostic_for_OPC.scl"))
        raw = open(res["path"], "rb").read()
        ok(raw.startswith(b"\xef\xbb\xbf"), "UTF-8 BOM (matches the exported template)")
        ok(raw.count(b"\n") > 0 and raw.count(b"\n") == raw.count(b"\r\n"), "CRLF only (no lone LF)")
        scl = raw.decode("utf-8-sig")
        ok('FUNCTION "06_Diagnostic for OPC"' in scl, "FUNCTION renamed")
        ok('"S1.CABINET001.STATE"(' in scl and "END_FUNCTION" in scl)
        ok('IN_00 := "DB"."A",' in scl, "plc_binding placed as IN_00")


def test_generate_diag_scl_missing_template():
    with tempfile.TemporaryDirectory() as d:
        res = diagnosis.generate_diag_scl([], d, io_path=None, template_path=os.path.join(d, "nope.scl"))
        ok(res["path"] is None and res["warnings"], "missing template -> warning, no file written")


# --- write + phase wiring ------------------------------------------------------------------ #

def test_generate_diag_list():
    # integration of the write path (uses the live diagnosis_logic_rules.csv, whose firing is
    # asserted separately with explicit rules); here we only assert the IO inventory + the files.
    with tempfile.TemporaryDirectory() as d:
        rows = [_row(in_diag=True, name_in_db="A", datablocks="01_PB"),
                _row(in_diag=True, script_type="DI1/2", diag_cabinet="002", diag_bit="00",
                     fu="=S1", loc="+SG1", dev="-B1"),
                _row(in_diag=False, name_in_db="Z", datablocks="01_PB")]
        res = diagnosis.generate_diag_list(rows, d, io_path=None)
        eq(res["io_count"], 2, "two in-diagnosis rows")
        ok(isinstance(res["logic_count"], int), "logic count comes from the live rules")
        ok(os.path.exists(res["io_path"]) and os.path.exists(res["logic_path"]))
        ok(res["io_path"].endswith("DiagList_IO.csv") and res["logic_path"].endswith("DiagList_Logic.csv"))
        back = csv_tables.read_rows(res["io_path"])
        eq(len(back), 2); ok("PLC_Binding" in back[0] and "Diag Cabinet" in back[0])


def test_phase_registered():
    p = registry().get(600)
    eq(p.number, 600); eq(p.key, "diagnosis"); eq(p.requires, (300,))
    eq([s.number for s in p.sub_phases], [610, 620])
    eq([b.number for b in p.buttons], [610, 620, 630, 640])


def test_phase_run():
    with tempfile.TemporaryDirectory() as d:
        ctx = PipelineContext(params={"io_list": {"path": os.path.join(d, "nope.xlsx")}},
                              out_root=os.path.join(d, "out"), emit=lambda *_a, **_k: None)
        ctx.rows = [_row(in_diag=True, script_type="A", diag_cabinet="001", diag_bit="00", type_hw="A",
                         name_in_db="A", datablocks="01_PB")]
        res = p600_diagnosis.run(ctx)
        diag_dir = config.out_path(ctx.out_root, "diagnosis_dir")
        db_dir = config.out_path(ctx.out_root, "blocks_import_dir")
        eq(res.artifacts["diagnosis_dir"], diag_dir)
        eq(res.artifacts["blocks_import_dir"], db_dir)
        ok(os.path.exists(os.path.join(diag_dir, "DiagList_IO.csv")))
        ok(os.path.exists(os.path.join(diag_dir, "DiagList_Logic.csv")))
        # the SCL needs the real template (committed under Shared/Templates); assert when present
        if os.path.exists(diagnosis.DIAG_SCL_TEMPLATE):
            ok(res.ok)
            ok(os.path.exists(os.path.join(db_dir, "Diagnostic_for_OPC.scl")))


if __name__ == "__main__":
    raise SystemExit(run("diagnosis", [
        ("build_diag_list_io", test_build_diag_list_io),
        ("diag_io_tag_binding", test_diag_io_tag_binding),
        ("logic_or_per_row", test_logic_or_per_row),
        ("logic_fires_on_any", test_logic_fires_on_any),
        ("logic_next_free_bit", test_logic_next_free_bit),
        ("logic_paired_channel_sibling", test_logic_paired_channel_sibling),
        ("logic_fld_fallback_cabinet", test_logic_fld_fallback_cabinet),
        ("logic_diag_desc_rule_override_and_fallback", test_logic_diag_desc_rule_override_and_fallback),
        ("logic_warning_family", test_logic_warning_family),
        ("generate_diag_list", test_generate_diag_list),
        ("ml_value", test_ml_value),
        ("node_of_and_fl_value", test_node_of_and_fl_value),
        ("render_scl", test_render_scl),
        ("render_scl_tristate_and_warning_split", test_render_scl_tristate_and_warning_split),
        ("generate_diag_scl", test_generate_diag_scl),
        ("generate_diag_scl_missing_template", test_generate_diag_scl_missing_template),
        ("phase_registered", test_phase_registered),
        ("phase_run", test_phase_run),
    ]))
