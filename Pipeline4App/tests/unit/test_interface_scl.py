"""Phase 400 - the MachineInterfaces SCL projection (domain/interface_scl.py): direction-templated
assignments, TIA quoting, REGION grouping, skip-with-WARN on blanks/unknown directions, and the
BOM/CRLF file shape. Hermetic (synthetic elements; the templates read from the builtin
generation_params.yaml)."""
import os
import tempfile

from _harness import run, eq, ok
from pipeline4.core.database import Database
from pipeline4.domain import interface_scl
from pipeline4.domain.interfaces import interface_elements_table, interfaces_table


def _element(**kw):
    row = {"interface": "SORTER-01", "category": "", "description": "", "functional_unit": "",
           "location": "", "device": "", "data_type": "BOOL", "direction": "Q", "offset_byte": 0,
           "bit": 0, "io_address_side1": "", "signal_name": "", "expression": "",
           "diag_cabinet": "", "swp_cabinet": "", "diag_bit": "", "source": "mirror",
           "source_signal": ""}
    row.update(kw)
    return row


def _db(elements):
    etab = interface_elements_table()
    for e in elements:
        etab.add(**e)
    return Database([interfaces_table(), etab])


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


def test_project_file_shape():
    with tempfile.TemporaryDirectory() as d:
        res = interface_scl.project(_db([
            _element(signal_name="PNC_Q_S1 HEARTBEAT", expression='"Clock 1Hz"', direction="Q"),
            _element(signal_name="PNC_I_S1 RUN", expression="TARGET", direction="I"),
        ]), out_dir=d)
        eq((res["assignments"], res["interfaces"]), (2, 1))
        raw = open(res["path"], "rb").read()
        ok(raw.startswith(b"\xef\xbb\xbf"), "UTF-8 BOM")
        ok(b"\r\n" in raw and b"\n" == raw[-1:], "CRLF lines")
        text = raw.decode("utf-8-sig")
        ok(text.startswith('FUNCTION "MachineInterfaces" : Void'), "the FUNCTION header")
        ok(text.rstrip().endswith("END_FUNCTION"), "the FUNCTION footer")
        ok('    "TARGET" := "PNC_I_S1 RUN";' in text.replace("\r\n", "\n"),
           "a bare expression target gets TIA-quoted like the signal side")
        eq(os.path.basename(res["path"]), "MachineInterfaces.scl", "the configured file name")


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
        ("project_file_shape", test_project_file_shape),
        ("project_no_elements_writes_nothing", test_project_no_elements_writes_nothing),
    ]))
