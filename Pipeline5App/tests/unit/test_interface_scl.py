"""Phase 400 - the MachineInterfaces SCL projection (domain/interface_scl.py): direction-templated
assignments, TIA quoting, REGION grouping, skip-with-WARN on blanks/unknown directions, and the
BOM/CRLF file shape. Hermetic (synthetic elements; the templates read from the builtin
generation_params.yaml)."""
import os
import tempfile

from _harness import run, eq, ok
from pipeline5.truth.database import Database
from pipeline5.systems.plc_based.siemens_s7 import interface_scl_emitter as interface_scl
from pipeline5.phases.interfaces.builder import interface_elements_table, interfaces_table


def _element(**kw):
    row = {"interface": "SORTER-01", "category": "", "description": "", "functional_unit": "",
           "location": "", "device": "", "data_type": "BOOL", "direction": "Q", "offset_byte": 0,
           "bit": 0, "io_address_side1": "", "signal_name": "", "expression": "",
           "diag_cabinet": "", "swp_cabinet": "", "diag_bit": "", "source": "mirror",
           "source_signal": ""}
    row.update(kw)
    return row


def _db(elements, interfaces=()):
    itab, etab = interfaces_table(), interface_elements_table()
    for i in interfaces:
        itab.add(**i)
    for e in elements:
        etab.add(**e)
    return Database([itab, etab])


def test_direction_templates_and_quoting():
    templates = interface_scl._scl_params()["templates"]
    lines, findings = interface_scl.render_lines([
        _element(signal_name="PNC_Q_S1 HEARTBEAT", expression='"Clock 1Hz"', direction="Q"),
        _element(signal_name="PNC_I_S1 RUN CMD", expression='"03_FDBACK"."x"', direction="I"),
    ], templates)
    eq(findings, [], "clean elements produce no findings")
    eq(lines[0], "REGION SORTER-01", "a REGION per interface")
    eq(lines[1], '    "PNC_Q_S1 HEARTBEAT" := "Clock 1Hz";',
       "'>' (Q): signal := expression; the bare tag quotes, the quoted expression stays")
    eq(lines[2], '    "03_FDBACK"."x" := "PNC_I_S1 RUN CMD";',
       "'<' (I): expression := signal; the qualified binding stays as-is")
    eq(lines[3], "END_REGION")


def test_region_grouping_first_seen():
    templates = interface_scl._scl_params()["templates"]
    lines, _f = interface_scl.render_lines([
        _element(interface="SORTER-01", signal_name="A", expression="E1"),
        _element(interface="SORTER+DIAG-02", signal_name="B", expression="E2"),
        _element(interface="SORTER-01", signal_name="C", expression="E3"),
    ], templates)
    regions = [ln for ln in lines if ln.startswith("REGION ")]
    eq(regions, ["REGION SORTER-01", "REGION SORTER+DIAG-02"], "interfaces group first-seen")
    body = "\n".join(lines)
    ok(body.index('"C"') < body.index("REGION SORTER+DIAG-02"), "C lands inside SORTER-01's region")


def test_blank_and_unknown_direction_warn_and_skip():
    templates = interface_scl._scl_params()["templates"]
    lines, findings = interface_scl.render_lines([
        _element(signal_name="", expression="X"),
        _element(signal_name="OK SIG", expression="OK EXPR", direction="Z"),
        _element(signal_name="GOOD", expression="RIGHT", direction="Q"),
    ], templates)
    eq(len(findings), 2, "one WARN per skipped element")
    eq({f.type for f in findings}, {"if_scl_blank_element", "if_scl_no_direction_template"})
    ok(all(f.severity == "WARN" for f in findings), "skips never halt")
    eq(sum(1 for ln in lines if ln.strip().endswith(";")), 1, "only the good element renders")


def test_byte_groups_get_blank_lines():
    templates = interface_scl._scl_params()["templates"]
    lines, _f = interface_scl.render_lines([
        _element(signal_name="A", expression="E1", io_address_side1="I10010.0"),
        _element(signal_name="B", expression="E2", io_address_side1="I10010.7"),
        _element(signal_name="C", expression="E3", io_address_side1="I10011.0"),
        _element(signal_name="D", expression="E4", io_address_side1="Q10026"),   # a WORD: its own byte
    ], templates)
    body = [ln for ln in lines if ln != "REGION SORTER-01" and ln != "END_REGION"]
    eq(body, ['    "A" := "E1";', '    "B" := "E2";', "", '    "C" := "E3";', "", '    "D" := "E4";'],
       "a blank line opens each NEW I/O byte; same-byte assignments stay together")


def test_project_file_shape():
    with tempfile.TemporaryDirectory() as d:
        legacy = os.path.join(d, "MachineInterfaces.scl")
        open(legacy, "w").write("stale")                       # the pre-rename output must not survive
        res = interface_scl.project(_db([
            _element(signal_name="PNC_Q_S1 HEARTBEAT", expression='"Clock 1Hz"', direction="Q"),
            _element(signal_name="PNC_I_S1 RUN", expression="TARGET", direction="I"),
        ]), out_dir=d)
        eq((res["assignments"], res["interfaces"]), (2, 1))
        raw = open(res["path"], "rb").read()
        ok(raw.startswith(b"\xef\xbb\xbf"), "UTF-8 BOM")
        ok(b"\r\n" in raw and b"\n" == raw[-1:], "CRLF lines")
        text = raw.decode("utf-8-sig")
        ok(text.startswith("//#!openn\r\n//#! kind: sw/source\r\n") and "//#! target: Program blocks\r\n" in text,
           "the contract-v1 header in its // wrapping opens the source")
        ok(text.split("//#!end\r\n", 1)[1].startswith('FUNCTION "10_Machine Interfaces" : Void'),
           "the FUNCTION is named after the configured file's stem")
        ok(text.rstrip().endswith("END_FUNCTION"), "the FUNCTION footer")
        ok('    "TARGET" := "PNC_I_S1 RUN";' in text.replace("\r\n", "\n"),
           "a bare expression target gets TIA-quoted like the signal side")
        eq(os.path.basename(res["path"]), "10_Machine Interfaces.scl", "the configured file name")
        ok(not os.path.exists(legacy), "the legacy MachineInterfaces.scl is swept (no double import)")


def test_the_description_opens_its_region():
    """C-033: the interface's description is its REGION's first line, a comment (the shipped
    `scl_region_comment`); an interface without one gets none; the comment opens no byte group and is no
    assignment - even when it ends in ';'."""
    eq(interface_scl._scl_params()["region_comment"], "    // {$description}", "the shipped template")
    with tempfile.TemporaryDirectory() as d:
        res = interface_scl.project(_db([
            _element(interface="SORTER-01", signal_name="A", expression="E1", io_address_side1="I10010.0"),
            _element(interface="SORTER-01", signal_name="B", expression="E2", io_address_side1="I10011.0"),
            _element(interface="SORTER-02", signal_name="C", expression="E3", io_address_side1="I11010.0"),
            _element(interface="SORTER-03", signal_name="D", expression="E4", io_address_side1="I12010.0"),
        ], interfaces=[{"instance": "SORTER-01", "description": "IO COUPLER - INTERFACE SAFETY (=TRIC) / COY LOWER"},
                       {"instance": "SORTER-02", "description": ""},
                       {"instance": "SORTER-03", "description": "ENDS IN;"}]), out_dir=d)
        text = open(res["path"], encoding="utf-8-sig").read().replace("\r\n", "\n")
    body = text.split("BEGIN\n", 1)[1].split("END_FUNCTION", 1)[0].splitlines()
    eq(body, ["REGION SORTER-01", "    // IO COUPLER - INTERFACE SAFETY (=TRIC) / COY LOWER",
              '    "A" := "E1";', "", '    "B" := "E2";', "END_REGION", "",
              "REGION SORTER-02", '    "C" := "E3";', "END_REGION", "",
              "REGION SORTER-03", "    // ENDS IN;", '    "D" := "E4";', "END_REGION"])
    eq((res["assignments"], res["interfaces"]), (4, 3), "the comments are no assignments")


def test_the_region_comment_is_config():
    """C-033: the comment line is the project's template ($description, $interface); a blank render or a blank
    description writes no line; a project config without the key is a located error."""
    from pipeline5 import config
    rows = [{"instance": "SORTER-01", "description": "LOWER"}, {"instance": "SORTER-02", "description": "  "}]
    eq(interface_scl.region_comments(rows, "    // {$interface}: {$description}"), {"SORTER-01": "    // SORTER-01: LOWER"})
    eq(interface_scl.region_comments(rows, "{}"), {}, "a template rendering blank writes nothing")
    original = config.load_generation_params
    config.load_generation_params = lambda: {"interfaces": {"scl_file": "x.scl", "scl_line_templates": {}}}
    try:
        interface_scl._scl_params()
        ok(False, "a missing key must raise")
    except RuntimeError as error:
        ok("interfaces.scl_region_comment" in str(error), str(error))
    finally:
        config.load_generation_params = original


def test_project_no_elements_writes_nothing():
    with tempfile.TemporaryDirectory() as d:
        res = interface_scl.project(_db([]), out_dir=d)
        eq((res["path"], res["assignments"]), ("", 0))
        eq(os.listdir(d), [], "nothing written")


if __name__ == "__main__":
    import sys
    sys.exit(run("interface_scl", [
        ("direction_templates_and_quoting", test_direction_templates_and_quoting),
        ("region_grouping_first_seen", test_region_grouping_first_seen),
        ("blank_and_unknown_direction_warn_and_skip", test_blank_and_unknown_direction_warn_and_skip),
        ("byte_groups_get_blank_lines", test_byte_groups_get_blank_lines),
        ("project_file_shape", test_project_file_shape),
        ("project_no_elements_writes_nothing", test_project_no_elements_writes_nothing),
        ("the_description_opens_its_region", test_the_description_opens_its_region),
        ("the_region_comment_is_config", test_the_region_comment_is_config),
    ]))
