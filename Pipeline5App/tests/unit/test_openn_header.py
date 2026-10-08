"""The OP5 contract-v1 header (openn_header, Shared/PL5_OP5_contract.md §3) and the workspace layout (§4):
the three wrappings, the key rules of the spec, the round trip through the parser that mirrors OP5's
reference implementation (Excel padding / quoting undone, duplicates refused, unknown keys tolerated, a
bare `#!format=N` = Legacy), the run id + the workspace config, and the Siemens layout's placement
(the PLC folder from the staged facts, the delivery dirs, one config write per generation)."""
import datetime
import os
import tempfile

from _harness import run, eq, ok, raises
from pipeline5.config import paths as p5paths
from pipeline5.systems.plc_based.siemens_s7 import openn_header as header
from pipeline5.systems.plc_based.siemens_s7.output_layout import LAYOUT, TiaOutputLayout


def _pin_clock():
    header.clock = lambda: datetime.datetime(2026, 10, 8, 12, 30, 45, tzinfo=datetime.timezone.utc)


def test_fields_and_csv_rendering():
    _pin_clock()
    header.begin_run("20261008-123045-beef")
    f = header.fields("hw/stations", 700, project="8XXX", target="Devices & networks", source="hardware_stations")
    eq(header.render_csv(f).split("\r\n"),
       ["#!openn", "#! kind: hw/stations", "#! schema: 2", "#! producer: Pipeline5 5.0 (phase 700)",
        "#! generated: 2026-10-08T12:30:45Z", "#! run: 20261008-123045-beef", "#! project: 8XXX",
        "#! target: Devices & networks", "#! source: hardware_stations", "#!end", ""],
       "the spec's shape: #!openn, `#! key: value` lines in the spec's order, #!end, CRLF, no padding")
    eq(header.fields("hw/modules")["schema"], "2", "the hardware csvs continue the format-2 numbering")
    eq(header.fields("sw/data-block", 520)["schema"], "1", "everything else is schema 1")
    ok("plc" not in header.fields("sw/source", 400), "an optional key not given is not written")
    eq(header.fields("sw/source", 400, project="")["project"] if "project" in header.fields("sw/source", 400, project="") else None,
       None, "an explicitly empty project is omitted, not written blank")
    raises(ValueError, lambda: header.fields("sw/nope", 1))


def test_csv_value_rules():
    f = header.fields("hw/stations", 700, comment="trailing,")
    raises(ValueError, lambda: header.render_csv(f))             # Excel's padding strip would eat it
    ok(header.render_csv(f, delimiter=";"), "another delimiter: fine")
    ok("#! comment: a b" in header.render_csv(header.fields("hw/stations", 700, comment="a\r\nb")),
       "line breaks become spaces (a value is one line)")
    raises(ValueError, lambda: header.render_csv({"Bad Key": "x"}))


def test_xml_and_source_wrappings():
    _pin_clock()
    f = header.fields("sw/data-block", 520, plc="n0001", target="Program blocks", comment="x--y")
    xml = header.render_xml(f)
    ok(xml.startswith("<!--\r\n#!openn\r\n") and xml.endswith("#!end\r\n-->\r\n"), "one comment, CRLF")
    ok("#! comment: x- -y" in xml, "`--` is illegal inside an XML comment")
    doc = '<?xml version="1.0" encoding="utf-8"?>\r\n<Document>\r\n</Document>'
    stamped = header.stamp_xml(doc, f)
    ok(stamped.startswith('<?xml version="1.0" encoding="utf-8"?>\r\n<!--\r\n#!openn\r\n'),
       "the first comment after the declaration")
    ok(stamped.endswith("-->\r\n<Document>\r\n</Document>"), "the document follows untouched")
    again = header.stamp_xml(stamped, header.fields("sw/block-template", 820))
    eq(again.count("#!openn"), 1, "re-stamping replaces the header, never stacks a second one")
    ok("sw/block-template" in again and "sw/data-block" not in again)
    ok(header.stamp_xml("﻿" + doc, f).startswith("﻿<?xml"), "a BOM stays first")
    marked = header.stamp_xml('<?xml version="1.0"?>\r\n<!--Begin Template-->\r\n<Document/>', f)
    ok(marked.count("<!--Begin Template-->") == 1 and marked.index("#!openn") < marked.index("<!--Begin Template-->"),
       "a template-marker comment is not a header: kept, the header goes before it")
    src = header.stamp_source('FUNCTION "X" : Void\r\nEND_FUNCTION\r\n', header.fields("sw/source", 400))
    ok(src.startswith("//#!openn\r\n//#! kind: sw/source\r\n") and "//#!end\r\nFUNCTION" in src,
       "every header line prefixed //, the source follows")
    eq(header.stamp_source(src, header.fields("sw/source", 620)).count("#!openn"), 1, "a source re-stamp replaces")
    eq(header.strip_header(src), 'FUNCTION "X" : Void\r\nEND_FUNCTION\r\n', "strip_header undoes a source stamp")
    eq(header.strip_header(stamped), doc, "...an XML stamp")
    eq(header.strip_header("#!format=2,,,,\r\n# Role\r\nPlc,n1\r\n"), "# Role\r\nPlc,n1\r\n", "...and the legacy tag")
    csv = header.stamp_csv("#!format=2,,,,\r\n# Role\r\n", header.fields("hw/stations", 700))
    ok(csv.startswith("#!openn\r\n") and "#!format" not in csv and csv.endswith("#!end\r\n# Role\r\n"),
       "a csv stamp replaces the legacy tag line")


def test_round_trip_through_the_op5_rules():
    _pin_clock()
    f = header.fields("sw/block-gen", 820, plc="n0001-mc1-cc1-k65501", target="Program blocks",
                      comment="Pipeline5 5.0, phase 820")
    for text, syntax in ((header.render_csv(f) + "$,template=Templates/x.xml\r\n", "csv"),
                         (header.stamp_xml('<?xml version="1.0"?>\r\n<Document/>', f), "xml"),
                         (header.render_source(f) + "FUNCTION\r\n", "source")):
        h = header.parse_directives(header.directive_lines_of(text, syntax))
        eq(h.status, "ok", f"{syntax}: {h.problems}")
        eq(h.values, f, f"{syntax}: every key and value survives the round trip")
    # Excel saved the csv: every line padded with the delimiter, the line holding a comma quoted
    excel = ('#!openn,,,,\r\n#! kind: sw/block-gen,,,,\r\n#! schema: 1,,,,\r\n'
             '"#! producer: Pipeline5 5.0, phase 820",,,,\r\n#! generated: 2026-10-08T12:30:45Z,,,,\r\n'
             '# a plain comment between header lines,,,,\r\n#!end,,,,\r\n$,template=x\r\n')
    h = header.parse_directives(header.directive_lines_of(excel, "csv"))
    eq(h.status, "ok", h.problems)
    eq(h.get("producer"), "Pipeline5 5.0, phase 820", "the quoting and the padding are undone")
    eq(header.normalize_csv_line('"a ""b"" c",,,'), 'a "b" c')
    eq(header.normalize_csv_line("#! kind: x;;;\t"), "#! kind: x", "semicolon / tab padding too")


def test_parser_rules():
    eq(header.parse_directives(["#!format=2"]).status, "legacy", "a bare format tag is Legacy")
    eq(header.parse_directives(["#!format=2"]).legacy_format, 2)
    eq(header.parse_directives([]).status, "missing")
    good = ["#!openn", "#! kind: hw/stations", "#! schema: 2", "#! producer: p", "#! generated: 2026-10-08T00:00:00Z"]
    dup = header.parse_directives(good + ["#! kind: hw/modules", "#!end"])
    eq(dup.status, "invalid")
    ok(any("duplicate header key: kind" in p for p in dup.problems), dup.problems)
    unclosed = header.parse_directives(good)
    ok(unclosed.status == "invalid" and any("not closed" in p for p in unclosed.problems), unclosed.problems)
    missing = header.parse_directives(["#!openn", "#! kind: hw/stations", "#!end"])
    ok(any("missing required header key: schema" in p for p in missing.problems), missing.problems)
    extra = header.parse_directives(["#!openn", "#! KIND: hw/stations", "#! schema: 2", "#! producer: p",
                                     "#! generated: 2026-10-08T00:00:00Z", "#! flavour: x", "#!end"])
    eq(extra.status, "ok", extra.problems)
    eq(extra.get("kind"), "hw/stations", "keys are case-insensitive")
    ok(any("unknown header key: flavour" in r for r in extra.remarks), "an unknown key is a remark, not an error")
    bad = header.parse_directives(good[:1] + ["#! kind: hw/stations", "#! schema: two", "#! producer: p",
                                              "#! generated: yesterday", "#!end"])
    ok(any("schema is not an integer" in p for p in bad.problems) and any("ISO 8601" in p for p in bad.problems), bad.problems)
    newer = header.parse_directives(["#!openn", "#! contract: 1", "#! producer: p", "#! generated: 2026-10-08T00:00:00Z", "#!end"],
                                    header.WORKSPACE_REQUIRED)
    eq(newer.status, "ok", "the workspace config has no kind")
    eq(header.parse_directives(["#!openn", "#! producer: p", "#!end"], header.WORKSPACE_REQUIRED).status, "invalid")


def test_sidecar_and_read_header():
    with tempfile.TemporaryDirectory() as d:
        xlsx = os.path.join(d, "PLCTags.xlsx")
        open(xlsx, "wb").write(b"PK\x03\x04")
        side = header.write_sidecar(xlsx, header.fields("doc/plc-tags-workbook", 510, plc="n1", target="PLC tags"))
        eq(side, xlsx + ".openn")
        h = header.read_header(xlsx)
        eq((h.status, h.get("kind"), h.get("target"), h.get("plc")), ("ok", "doc/plc-tags-workbook", "PLC tags", "n1"))
        ok(any("sidecar" in r for r in h.remarks), "the header came from the sidecar")
        csv_path = os.path.join(d, "Stations.csv")
        with open(csv_path, "w", newline="") as f:
            f.write(header.render_csv(header.fields("hw/stations", 700)) + "# Role\r\n")
        eq(header.read_header(csv_path).get("kind"), "hw/stations")
        eq(header.read_header(os.path.join(d, "nope.csv")).status, "invalid", "an unreadable file: invalid, no crash")
        eq(header.syntax_for("x.db"), "source")
        eq(header.syntax_for("x.xlsm"), "sidecar")


def test_run_id_and_workspace_config():
    rid = header.new_run_id(datetime.datetime(2026, 10, 8, 1, 2, 3, tzinfo=datetime.timezone.utc))
    ok(rid.startswith("20261008-010203-") and len(rid) == len("20261008-010203-abcd"), rid)
    eq(header.begin_run("fixed-1"), "fixed-1")
    eq(header.current_run(), "fixed-1", "every writer stamps the begun run")
    ok(header.begin_run() != "fixed-1", "begin_run() without an id mints a fresh one")
    with tempfile.TemporaryDirectory() as d:
        _pin_clock()
        path = header.write_workspace_config(os.path.join(d, ".openn", "workspace.openn.config"),
                                             header.workspace_fields(run="r9", project="8XXX", plcs=["n1", "n2"]))
        text = open(path, encoding="utf-8", newline="").read()
        eq(text, "#!openn\r\n#! contract: 1\r\n#! producer: Pipeline5 5.0\r\n#! generated: 2026-10-08T12:30:45Z\r\n"
                 "#! run: r9\r\n#! project: 8XXX\r\n#! plcs: n1, n2\r\n#! templates: Templates\r\n#!end\r\n",
           "the §3.4 shape")


def test_layout_plc_folder_and_dirs():
    eq(TiaOutputLayout.plc_folder({"hardware_stations": [{"role": "IoDevice", "station_name": "n6"},
                                                         {"role": "Plc", "station_name": "n0001-mc1-cc1-k65501"}]}),
       "n0001-mc1-cc1-k65501", "the Plc station row of hardware_stations")
    eq(TiaOutputLayout.plc_folder({"signals": [{"script_type": "A", "profinet_name": "x"},
                                               {"script_type": "PLC", "profinet_name": "n1"}]}),
       "n1", "else the PLC head of the staged signals (phase 700's rule)")
    raises(RuntimeError, lambda: TiaOutputLayout.plc_folder({"signals": []}))
    eq(TiaOutputLayout.plc_folder({"signals": []}, required=False), None)
    orig = p5paths._BUILTIN_OUTPUT
    with tempfile.TemporaryDirectory() as d:
        p5paths._BUILTIN_OUTPUT = d
        try:
            root = os.path.join(d, "TiaPortalProjectInterface", "BuilderData")
            dirs = LAYOUT.delivery_dirs({"signals": [{"script_type": "PLC", "profinet_name": "n1"}]})
            eq(dirs["workspace"], root)
            eq(dirs["hardware"], os.path.join(root, "Devices & networks"))
            eq(dirs["templates"], os.path.join(root, "Templates"))
            eq(dirs["blocks_import"], os.path.join(root, "n1", "Program blocks"))
            eq(dirs["blocks_creation"], dirs["blocks_import"], "one Program blocks folder (the VCI shape)")
            eq(dirs["io_tags"], os.path.join(root, "n1", "PLC tags"))
            eq(dirs["plc"], "n1")
            eq(LAYOUT.dirs()["blocks_import"], root, "nothing on disk yet: the open buttons point at the workspace")
            os.makedirs(os.path.join(root, "n1", "Program blocks"))
            os.makedirs(os.path.join(root, "Templates"))
            os.makedirs(os.path.join(root, ".openn"))
            eq(LAYOUT.plc_folders_on_disk(), ["n1"], "the reserved root folders are not PLCs")
            eq(LAYOUT.dirs()["io_tags"], os.path.join(root, "n1", "PLC tags"))
        finally:
            p5paths._BUILTIN_OUTPUT = orig


def test_begin_generation_writes_the_config_once_per_run():
    orig = p5paths._BUILTIN_OUTPUT
    db = {"signals": [{"script_type": "PLC", "profinet_name": "n1"}]}
    with tempfile.TemporaryDirectory() as d:
        p5paths._BUILTIN_OUTPUT = d
        try:
            layout = TiaOutputLayout()
            eq(layout.begin_generation(db, "host-run-1"), ("host-run-1", True), "the host's id is adopted, the config written")
            eq(header.current_run(), "host-run-1", "...and every writer stamps it from now on")
            h = header.read_header(layout.config_path(), header.WORKSPACE_REQUIRED)
            eq((h.status, h.get("run"), h.get("plcs"), h.get("contract")), ("ok", "host-run-1", "n1", "1"))
            eq(layout.begin_generation(db, "host-run-1"), ("host-run-1", False), "a later phase of the same Run-all joins it")
            run2, written2 = layout.begin_generation(db, "")
            ok(written2 and run2 != "host-run-1", "no host id (a headless caller): a fresh id, a new config")
            eq(header.read_header(layout.config_path(), header.WORKSPACE_REQUIRED).get("run"), run2)
        finally:
            p5paths._BUILTIN_OUTPUT = orig


if __name__ == "__main__":
    import sys
    sys.exit(run("openn_header", [
        ("fields_and_csv_rendering", test_fields_and_csv_rendering),
        ("csv_value_rules", test_csv_value_rules),
        ("xml_and_source_wrappings", test_xml_and_source_wrappings),
        ("round_trip_through_the_op5_rules", test_round_trip_through_the_op5_rules),
        ("parser_rules", test_parser_rules),
        ("sidecar_and_read_header", test_sidecar_and_read_header),
        ("run_id_and_workspace_config", test_run_id_and_workspace_config),
        ("layout_plc_folder_and_dirs", test_layout_plc_folder_and_dirs),
        ("begin_generation_writes_the_config_once_per_run", test_begin_generation_writes_the_config_once_per_run),
    ]))
