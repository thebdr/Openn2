"""M7 gate (data-independent): Phase 500 / 510 Generate I/O Tags.

build_io_tags (resolved I/O signals from the staged identity columns), interface_tags (reading the
IF_ sheets phase 400 inserts into the I/O List), the data-type mapping, the combined PLCTags.xlsx
write, and the phase wiring (registration + run -> artifact/file). 520 (data blocks) is tested
separately when built.
"""
import os
import tempfile
import xml.etree.ElementTree as ET
from _harness import run, eq, ok
from openpyxl import Workbook, load_workbook
from openpyxl.utils import column_index_from_string as CI
from openpyxl.worksheet.table import Table

from pipeline3.core import config
from pipeline3.context import PipelineContext
from pipeline3.domain import signals
import pipeline3.phases  # registers all phases
from pipeline3.phases import p500_signals
from pipeline3.registry import registry


def _io_row(name_in_tagtable="", tagtable="", bit="I0.0", io_comment="", device="-K1"):
    """A staged-database row carrying the identity columns 510 reuses."""
    return {"name_in_tagtable": name_in_tagtable, "tagtable": tagtable, "bit": bit,
            "functional_unit": "=S1", "location": "+L1", "device": device,
            "script_type": "A", "_type": {"io_comment": io_comment}}


def _make_iolist(path):
    """A synthetic I/O List: one NET SAFETY sheet (a non-IF_ table, must be ignored), one IF_ sheet
    with an interface signals table, and an IF_ sheet with no table (-> warning)."""
    wb = Workbook()
    # a non-interface sheet that DOES carry the signal headers - must be ignored (not IF_-prefixed)
    ns = wb.active
    ns.title = "NET SAFETY 50"
    _fill_signals_table(ns, "NS_SIGNALS", [("Z", "BOOL", ">", 0, 0, "Q9.0", "SHOULD_NOT_APPEAR", "x")])

    sh = wb.create_sheet("IF_SORTER-01")
    _fill_signals_table(sh, "SORTER_SIGNALS_IF_SORTER_01", [
        ("B", "BOOL", ">", 0, 0, "Q10000.0", "PNC_Q_SORTER-01 HEARTBEAT", "Blinking 1Hz"),
        ("",  "",     "",  "", "", "",         "",                          ""),            # separator
        ("SPD", "WORD", ">", 2, "", "Q10002.0", "PNC_Q_SORTER-01 SPEED",    "Speed word"),
        ("B", "BOOL", ">", 1, 0, "",          "PNC_Q_SORTER-01 NO_ADDR",   "unresolved"),  # no addr -> warn
        ("B", "BOOL", "<", 0, 0, "I10000.0", "PNC_I_SORTER-01 RUNNING",   "Running"),
        ("",  "",     "",  "", "", "",         "",                          ""),            # trailing sep
    ])

    no = wb.create_sheet("IF_NOTABLE")
    no["A1"] = "no signals table here"
    wb.save(path)


def _fill_signals_table(ws, table_name, rows):
    cols = ["Category", "Data Type", "Direction </>", "I/O Offset Byte", "I/O Bit",
            "I/O Address Side 1", "Signal Name Side 1", "Description"]
    for i, h in enumerate(cols, start=1):
        ws.cell(1, i, h)
    for r, vals in enumerate(rows, start=2):
        for c, v in enumerate(vals, start=1):
            if v != "":
                ws.cell(r, c, v)
    last = 1 + len(rows)
    ws.add_table(Table(displayName=table_name, ref=f"A1:H{last}"))


# --- (510a) resolved I/O signals ----------------------------------------------------------- #

def test_build_io_tags():
    rows = [
        _io_row("TAG_A", "SafetyTags", "I0.0", io_comment="cmt {device}", device="-K1"),
        _io_row("", "", "I0.1"),                                   # untagged -> skipped
        _io_row("TAG_B", "", "Q5.2"),                              # blank tagtable -> falls back to script_type
    ]
    tags = signals.build_io_tags(rows)
    eq([t["name"] for t in tags], ["TAG_A", "TAG_B"], "only rows with a name_in_tagtable")
    eq(tags[0]["path"], "SafetyTags")
    eq(tags[0]["address"], "%I0.0", "bit %-prefixed")
    eq(tags[0]["data_type"], "Bool")
    eq(tags[0]["comment"], "cmt -K1", "comment from the type io_comment template")
    eq(tags[1]["path"], "A", "blank tagtable -> script_type fallback")
    eq(tags[1]["address"], "%Q5.2")


# --- (510b) interface tags from the IF_ sheets --------------------------------------------- #

def test_interface_tags():
    with tempfile.TemporaryDirectory() as d:
        iol = os.path.join(d, "iolist.xlsx"); _make_iolist(iol)
        tags, warnings = signals.interface_tags(iol)
        names = [t["name"] for t in tags]
        eq(names, ["PNC_Q_SORTER-01 HEARTBEAT", "PNC_Q_SORTER-01 SPEED", "PNC_I_SORTER-01 RUNNING"],
           "named rows WITH a resolved address, IF_ sheets only (NET SAFETY ignored)")
        ok(all(t["path"] == "IF_SORTER-01" for t in tags), "Path = the IF_ sheet name")
        eq(tags[0]["address"], "%Q10000.0", "cached address %-prefixed")
        eq(tags[2]["address"], "%I10000.0")
        eq(tags[1]["data_type"], "Word", "WORD -> Word")
        eq(tags[0]["data_type"], "Bool")
        eq(tags[0]["comment"], "Blinking 1Hz", "comment from Description")
        ok(any("NO_ADDR" in w and "no resolved" in w for w in warnings), "named-but-address-less row warned")
        ok(any("IF_NOTABLE" in w for w in warnings), "an IF_ sheet without a signals table is warned")
        ok(not any("SHOULD_NOT_APPEAR" in str(t) for t in tags), "non-IF_ sheet not read")


def test_interface_tags_absent():
    eq(signals.interface_tags(None), ([], []), "no path -> nothing")
    eq(signals.interface_tags(r"C:\nope\missing.xlsx"), ([], []), "missing file -> nothing")
    with tempfile.TemporaryDirectory() as d:
        iol = os.path.join(d, "plain.xlsx")
        wb = Workbook(); wb.active.title = "NET SAFETY 50"; wb.save(iol)
        eq(signals.interface_tags(iol), ([], []), "no IF_ sheets -> no interface tags")


def test_tia_dtype():
    eq(signals._tia_dtype("BOOL"), "Bool"); eq(signals._tia_dtype("WORD"), "Word")
    eq(signals._tia_dtype("dword"), "DWord"); eq(signals._tia_dtype(""), "Bool", "blank defaults Bool")
    eq(signals._tia_dtype("Custom"), "Custom", "unknown capitalized")


def test_group_tables():
    tags = [{"path": "A", "name": "x"}, {"path": "B", "name": "y"}, {"path": "A", "name": "z"}]
    g = signals.group_tables(tags)
    eq(sorted(g), ["A", "B"]); eq([t["name"] for t in g["A"]], ["x", "z"], "order preserved")


# --- write + combined generate ------------------------------------------------------------- #

def test_write_plc_tags():
    with tempfile.TemporaryDirectory() as d:
        tables = {"SafetyTags": [{"name": "T1", "data_type": "Bool", "address": "%I0.0", "comment": "c1"}],
                  "IF_SORTER-01": [{"name": "PNC1", "data_type": "Word", "address": "%Q10000.0", "comment": "d1"}]}
        path, total = signals.write_plc_tags(tables, d)
        eq(total, 2); ok(os.path.exists(path) and path.endswith("PLCTags.xlsx"))
        wb = load_workbook(path)
        eq(wb.sheetnames, ["PLC Tags", "TagTable Properties"])
        ws = wb["PLC Tags"]
        eq([c.value for c in ws[1]], signals.TAG_COLUMNS, "header row")
        body = [[c.value for c in row] for row in ws.iter_rows(min_row=2)]
        eq(len(body), 2)
        # sorted by Path: IF_SORTER-01 before SafetyTags
        eq(body[0][:5], ["PNC1", "IF_SORTER-01", "Word", "%Q10000.0", "d1"])
        eq(body[0][5:8], ["True", "True", "True"], "Hmi flags text True")
        eq(body[1][:5], ["T1", "SafetyTags", "Bool", "%I0.0", "c1"])
        props = [[c.value for c in row] for row in wb["TagTable Properties"].iter_rows(min_row=2)]
        eq([p[0] for p in props], ["IF_SORTER-01", "SafetyTags"], "distinct tables listed sorted")
        wb.close()


def test_generate_io_tags_combined():
    with tempfile.TemporaryDirectory() as d:
        iol = os.path.join(d, "iolist.xlsx"); _make_iolist(iol)
        rows = [_io_row("TAG_A", "SafetyTags", "I0.0"), _io_row("TAG_B", "SafetyTags", "Q1.0")]
        res = signals.generate_io_tags(rows, d, iolist_path=iol)
        eq(res["io_count"], 2, "two resolved I/O signals")
        eq(res["iface_count"], 3, "three interface tags from IF_SORTER-01")
        eq(res["total"], 5)
        eq(res["tables"], ["IF_SORTER-01", "SafetyTags"])
        ok(any("NO_ADDR" in w for w in res["warnings"]))
        ws = load_workbook(res["path"])["PLC Tags"]
        eq(ws.max_row, 6, "header + 5 tags")


def test_clear_on_rerun():
    with tempfile.TemporaryDirectory() as d:
        tables = {"T": [{"name": "x", "data_type": "Bool", "address": "%I0.0", "comment": ""}]}
        path, _ = signals.write_plc_tags(tables, d)
        tag_dir = os.path.dirname(path)
        stale = os.path.join(tag_dir, "old.csv"); open(stale, "w").write("x")
        signals.write_plc_tags(tables, d)
        ok(not os.path.exists(stale), "prior *.csv swept on re-run")


# --- 520 Generate Data Blocks -------------------------------------------------------------- #

def _db_row(script_type="DI1/2", name_in_db="Door Closed", datablocks="07_DOOR", db_kind="safe_db",
            io_comment="", fu="=S1", loc="+SG1", dev="-B1"):
    return {"script_type": script_type, "name_in_db": name_in_db, "datablocks": datablocks,
            "functional_unit": fu, "location": loc, "device": dev,
            "_type": {"db_kind": db_kind, "io_comment": io_comment}}


_DB_RULES = [{"name": "Door Alarm", "required_types": ["DI1/2", "DI2/2"], "dev_type": "A",
              "db_name": "07_DOOR", "member": "Door Alarm [ {functional_unit}{location}{device} ]",
              "interface_tagname": ""}]


def test_build_data_blocks():
    rows = [
        _db_row("DI1/2", "Door Closed A", "07_DOOR", "safe_db", io_comment="closed {device}", dev="-B1"),
        _db_row("DI2/2", "Door Closed B", "07_DOOR", "safe_db", dev="-B2"),
        _db_row("KQ", "Contactor FB", "03_FDBACK", "safe_db"),
        _db_row("KQ", "Contactor FB", "03_FDBACK", "safe_db"),               # duplicate -> dropped
        _db_row("PA", "Node X", "PROFINET_NODES_ALARM", "db"),               # non-safe
        _db_row("X", "", ""),                                                # no name_in_db -> ignored
    ]
    dbs, warnings = signals.build_data_blocks(rows, _DB_RULES)
    eq(sorted(dbs), ["03_FDBACK", "07_DOOR", "PROFINET_NODES_ALARM"])
    eq(dbs["07_DOOR"]["safe"], True, "DI safe_db -> fail-safe DB")
    eq(dbs["PROFINET_NODES_ALARM"]["safe"], False, "db kind -> not fail-safe")
    doors = [m["name"] for m in dbs["07_DOOR"]["members"]]
    eq(doors[:len(signals.DB_CONSTANTS)], signals.DB_CONSTANTS, "constants first (Always FALSE/TRUE/No Operation)")
    ok("Door Closed A" in doors and "Door Closed B" in doors, "type-based members")
    ok("Door Alarm [ =S1+SG1-B1 ]" in doors and "Door Alarm [ =S1+SG1-B2 ]" in doors, "rule-driven members")
    fb = [m["name"] for m in dbs["03_FDBACK"]["members"]]
    eq(fb.count("Contactor FB"), 1, "duplicate DB member collapsed to one")
    ok(any("Contactor FB" in w and "contributed 2 times" in w for w in warnings), "dup reported")
    # type-member comment from io_comment
    cm = next(m for m in dbs["07_DOOR"]["members"] if m["name"] == "Door Closed A")
    eq(cm["comment"], "closed -B1")


def test_constants_spelling():
    eq(signals.DB_CONSTANTS, ["Always FALSE", "Always TRUE", "No Operation"], "space, no underscore")


def test_write_safe_db_xml():
    # a SAFE DB is exported as an F_DB Openness XML (the .db cannot express fail-safe)
    with tempfile.TemporaryDirectory() as d:
        rows = [_db_row("DI1/2", "Door Closed A", "07_DOOR", "safe_db", dev="-B1")]
        dbs, _ = signals.build_data_blocks(rows, _DB_RULES)
        db_dir, count = signals.write_data_blocks(dbs, d)
        eq(count, 1)
        ok(os.path.exists(os.path.join(db_dir, "07_DOOR.xml")), "safe DB -> .xml")
        ok(not os.path.exists(os.path.join(db_dir, "07_DOOR.db")), "no .db for a safe DB")
        raw = open(os.path.join(db_dir, "07_DOOR.xml"), "rb").read()
        ok(raw.startswith(b"\xef\xbb\xbf"), "UTF-8 BOM (matches a real TIA export)")
        ok(raw.count(b"\n") > 0 and raw.count(b"\n") == raw.count(b"\r\n"), "CRLF only (no lone LF)")
        ok(not raw.rstrip(b"\r\n>").endswith(b"\n"), "no trailing newline after </Document>")
        xtxt = raw.decode("utf-8-sig")
        ok("<ProgrammingLanguage>F_DB</ProgrammingLanguage>" in xtxt, "F_DB fail-safe marker")
        ok("<DBAccessibleFromOPCUA>false</DBAccessibleFromOPCUA>" in xtxt, "safe DB not OPC-UA accessible")
        ok("<Name>07_DOOR</Name>" in xtxt, "DB name")
        ok('<Member Name="Door Closed A"' in xtxt, "type member emitted")
        ok('<Member Name="Always FALSE"' in xtxt and '<Member Name="Always TRUE"' in xtxt, "constants kept")
        ok('<Member Name="Door Alarm [ =S1+SG1-B1 ]"' in xtxt, "rule-driven member present")
        ok("<MemoryLayout>Optimized</MemoryLayout>" in xtxt)
        ok(xtxt.rstrip().endswith("</Document>"), "well-formed XML tail")
        ET.fromstring(xtxt)  # parses as valid XML


def test_write_normal_db_source():
    # a NORMAL DB stays a .db external source, OPC-UA accessible
    with tempfile.TemporaryDirectory() as d:
        rows = [_db_row("PA", "Node X", "PROFINET_NODES_ALARM", "db")]
        dbs, _ = signals.build_data_blocks(rows, [])
        db_dir, count = signals.write_data_blocks(dbs, d)
        eq(count, 1)
        ok(os.path.exists(os.path.join(db_dir, "PROFINET_NODES_ALARM.db")), "normal DB -> .db")
        raw = open(os.path.join(db_dir, "PROFINET_NODES_ALARM.db"), "rb").read()
        ok(raw.startswith(b"\xef\xbb\xbf"), "UTF-8 BOM")
        ok(raw.count(b"\n") > 0 and raw.count(b"\n") == raw.count(b"\r\n"), "CRLF only")
        prof = raw.decode("utf-8-sig")
        ok(prof.startswith('DATA_BLOCK "PROFINET_NODES_ALARM"\r\n'), "DATA_BLOCK header")
        ok("DB_Accessible_From_OPC_UA := 'TRUE'" in prof, "normal DB -> OPC-UA accessible")
        ok("S7_Optimized_Access := 'TRUE'" in prof and "NON_RETAIN" in prof, "header attrs")
        ok("   VAR " in prof and "   END_VAR" in prof, "VAR/END_VAR block")
        ok(prof.rstrip().endswith("END_DATA_BLOCK"), "well-formed tail")


def test_write_clears_db_and_xml_not_scl():
    with tempfile.TemporaryDirectory() as d:
        rows = [_db_row("PA", "Node X", "PROFINET_NODES_ALARM", "db")]
        dbs, _ = signals.build_data_blocks(rows, [])
        db_dir, _ = signals.write_data_blocks(dbs, d)
        scl = os.path.join(db_dir, "Diagnostic_for_OPC.scl"); open(scl, "w").write("keep me")
        stale_db = os.path.join(db_dir, "old.db"); open(stale_db, "w").write("x")
        stale_xml = os.path.join(db_dir, "old.xml"); open(stale_xml, "w").write("x")
        signals.write_data_blocks(dbs, d)
        ok(not os.path.exists(stale_db), "prior *.db swept")
        ok(not os.path.exists(stale_xml), "prior *.xml swept")
        ok(os.path.exists(scl), "the SCL (phase 620) is NOT swept")


def test_generate_data_blocks_real_rules():
    # uses the real datablock_elements_rules.csv via config.load_rules
    with tempfile.TemporaryDirectory() as d:
        rows = [_db_row("DI1/2", "Door Closed", "07_DOOR", "safe_db", dev="-B1")]
        res = signals.generate_data_blocks(rows, d)
        ok("07_DOOR" in res["dbs"]); ok("07_DOOR" in res["safe"])
        ok(res["count"] >= 1)
        ok(os.path.exists(os.path.join(res["dir"], "07_DOOR.xml")), "safe DB -> .xml")


# --- phase wiring -------------------------------------------------------------------------- #

def test_phase_registered():
    p = registry().get(500)
    eq(p.number, 500); eq(p.key, "signals"); eq(p.requires, (300,))
    eq([s.number for s in p.sub_phases], [510, 520])
    eq([b.number for b in p.buttons], [510, 520, 530, 540])


def test_phase_run():
    with tempfile.TemporaryDirectory() as d:
        iol = os.path.join(d, "iolist.xlsx"); _make_iolist(iol)
        ctx = PipelineContext(params={"io_list": {"path": iol}}, out_root=os.path.join(d, "out"))
        ctx.rows = [_io_row("TAG_A", "SafetyTags", "I0.0"),
                    _db_row("DI1/2", "Door Closed", "07_DOOR", "safe_db", dev="-B1")]
        res = p500_signals.run(ctx)
        ok(res.ok)
        tag_dir = config.out_path(ctx.out_root, "io_tags_dir")
        db_dir = config.out_path(ctx.out_root, "blocks_import_dir")
        eq(res.artifacts["io_tags_dir"], tag_dir)
        eq(res.artifacts["blocks_import_dir"], db_dir)
        ok(os.path.exists(os.path.join(tag_dir, "PLCTags.xlsx")))
        ok(os.path.exists(os.path.join(db_dir, "07_DOOR.xml")), "safe DB exported as F_DB XML")


def test_write_safe_db_xml_and_dedup():
    with tempfile.TemporaryDirectory() as d:
        p = signals.write_safe_db(d, signals.COM_DB, ["AREA 1 PB", "AREA 1 FDB", "AREA 1 PB"])  # dup last
        ok(p.endswith("02_COM.xml"), "02_COM.xml path")
        xml = open(p, encoding="utf-8-sig").read()
        ok("<ProgrammingLanguage>F_DB</ProgrammingLanguage>" in xml, "safe F_DB")
        ok("<DBAccessibleFromOPCUA>false</DBAccessibleFromOPCUA>" in xml, "not OPC-writable")
        eq(xml.count('<Member Name="AREA 1 PB"'), 1, "duplicate member dropped")
        ok(xml.index("AREA 1 PB") < xml.index("AREA 1 FDB"), "member order preserved")
        eq(signals.write_safe_db(d, signals.COM_DB, []), "", "no members -> no file written")


def test_sweep_preserves_zone_cumulative_db():
    with tempfile.TemporaryDirectory() as d:
        com = signals.write_safe_db(d, signals.COM_DB, ["AREA 1 PB"])
        ok(os.path.exists(com), "02_COM written")
        # a 520 write sweeps *.db/*.xml but must PRESERVE the phase-800-owned 02_COM.xml
        signals.write_data_blocks({"OTHER": {"safe": True, "members": [{"name": "x", "comment": ""}]}}, d)
        ok(os.path.exists(com), "02_COM preserved through the 520 sweep")
        db_dir = config.out_path(d, "blocks_import_dir")
        ok(os.path.exists(os.path.join(db_dir, "OTHER.xml")), "the 520-written DB present")


if __name__ == "__main__":
    raise SystemExit(run("signals", [
        ("build_io_tags", test_build_io_tags),
        ("interface_tags", test_interface_tags),
        ("interface_tags_absent", test_interface_tags_absent),
        ("tia_dtype", test_tia_dtype),
        ("group_tables", test_group_tables),
        ("write_plc_tags", test_write_plc_tags),
        ("generate_io_tags_combined", test_generate_io_tags_combined),
        ("clear_on_rerun", test_clear_on_rerun),
        ("build_data_blocks", test_build_data_blocks),
        ("constants_spelling", test_constants_spelling),
        ("write_safe_db_xml", test_write_safe_db_xml),
        ("write_normal_db_source", test_write_normal_db_source),
        ("write_clears_db_and_xml_not_scl", test_write_clears_db_and_xml_not_scl),
        ("generate_data_blocks_real_rules", test_generate_data_blocks_real_rules),
        ("write_safe_db_xml_and_dedup", test_write_safe_db_xml_and_dedup),
        ("sweep_preserves_zone_cumulative_db", test_sweep_preserves_zone_cumulative_db),
        ("phase_registered", test_phase_registered),
        ("phase_run", test_phase_run),
    ]))
