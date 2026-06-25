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

def _db_row(script_type="DI1/2", name_in_db="Door Closed", datablocks="07_DOOR", db_kind="F_DB",
            io_comment="", fu="=S1", loc="+SG1", dev="-B1"):
    return {"script_type": script_type, "name_in_db": name_in_db, "datablocks": datablocks,
            "functional_unit": fu, "location": loc, "device": dev,
            "_type": {"db_kind": db_kind, "io_comment": io_comment}}


def _db(prog_lang, *member_names):
    """A data-block dict (seeds + the given members) as datablocks.generate returns - a fixture for the
    write_data_blocks tests, independent of how the registry built it."""
    return {"prog_lang": prog_lang,
            "members": [{"name": c, "comment": ""} for c in signals.DB_CONSTANTS]
                       + [{"name": m, "comment": ""} for m in member_names]}


def test_db_kind_of_alignment():
    from pipeline3.domain import identity
    multi = {"db_kind": "DB|F_DB", "db_names": ["ALARM", "COMM"]}        # the | splitter, verbatim values
    eq(identity.db_kind_of(multi, "ALARM"), "DB", "positional: first db_name, verbatim")
    eq(identity.db_kind_of(multi, "COMM"), "F_DB", "positional: second db_name, verbatim")
    single = {"db_kind": "F_DB", "db_names": ["A", "B"]}
    eq(identity.db_kind_of(single, "A"), "F_DB", "a single kind applies to every DB")
    eq(identity.db_kind_of(single, "B"), "F_DB")
    ok(identity.is_db_backed(multi) and identity.is_db_backed(single), "non-empty db_kind -> DB-backed")
    ok(not identity.is_db_backed({"db_kind": ""}), "no db_kind -> not DB-backed")


def test_fdb_marker_canonicalized_and_unknown_warned():
    # the F_DB guardrail now lives in the registry path: a lowercase/padded db_programming_language meaning
    # F_DB is EMITTED as the canonical 'F_DB' (TIA-recognized) + OPC-locked by _db_xml; a genuinely
    # unrecognized value is written verbatim WITH a datablocks.generate warning.
    from pipeline3.domain import datablocks
    defs = [
        {"db_name": "SAFE_LC", "db_type": "Global", "db_programming_language": "f_db ", "for_each": ""},
        {"db_name": "WEIRD", "db_type": "Global", "db_programming_language": "ARRAY_DB", "for_each": ""},
    ]
    _g, _i, errs, warns = datablocks.generate([], defs, [], [])
    eq(errs, [], "no hard error - the verbatim ProgrammingLanguage is only a warning")
    safe = signals._db_xml("SAFE_LC", {"prog_lang": "f_db ", "members": []}, 1)
    ok("<ProgrammingLanguage>F_DB</ProgrammingLanguage>" in safe, "lowercase 'f_db ' -> canonical F_DB")
    ok("<DBAccessibleFromOPCUA>false</DBAccessibleFromOPCUA>" in safe, "and OPC-locked")
    weird = signals._db_xml("WEIRD", {"prog_lang": "ARRAY_DB", "members": []}, 1)
    ok("<ProgrammingLanguage>ARRAY_DB</ProgrammingLanguage>" in weird, "unrecognized stays verbatim")
    ok(any("ARRAY_DB" in w and "TIA may reject" in w for w in warns), "unrecognized db_programming_language warned")
    ok(not any("SAFE_LC" in w for w in warns), "the canonicalized F_DB does not warn")


def test_db_xml_config_attributes():
    # the config-driven path: a UDInt member with chosen attributes + DB attrs; a legacy Bool member stays
    # byte-identical (defaults reproduce the historical output).
    legacy = {"prog_lang": "DB", "members": [{"name": "Old", "comment": "x"}]}      # no datatype -> Bool
    cfg = {"prog_lang": "DB", "opc_ua": True, "webserver": True, "memory_layout": "Standard",
           "only_load_memory": True, "write_protected": True,
           "members": [{"name": "S1.CABINET001.STATE", "datatype": "UDInt", "retain": True,
                        "start_value": "0", "comment": "cab 1", "ext_accessible": True, "ext_visible": True,
                        "ext_writable": False, "setpoint": True}]}
    import xml.etree.ElementTree as ET
    lx = signals._db_xml("L", legacy, 1)
    ok('<Member Name="Old" Datatype="Bool" Remanence="NonRetain" Accessibility="Public">' in lx, "legacy member byte-stable")
    ok("<Comment>" not in lx and "IsOnlyStoredInLoadMemory" not in lx, "legacy DB carries no new elements")
    cx = signals._db_xml("DiagnosticTags", cfg, 2)
    ok('<Member Name="S1.CABINET001.STATE" Datatype="UDInt" Remanence="Retain"' in cx, "UDInt + Retain")
    ok('<BooleanAttribute Name="ExternalWritable" SystemDefined="true">false</BooleanAttribute>' in cx, "ext_writable=false")
    ok('<BooleanAttribute Name="SetPoint" SystemDefined="true">true</BooleanAttribute>' in cx, "setpoint=true")
    ok('<MultiLanguageText Lang="en-US">cab 1</MultiLanguageText>' in cx and "<StartValue>0</StartValue>" in cx, "comment + start value")
    ok("<MemoryLayout>Standard</MemoryLayout>" in cx, "memory layout")
    ok("<IsOnlyStoredInLoadMemory>true</IsOnlyStoredInLoadMemory>" in cx
       and "<IsWriteProtectedInAS>true</IsWriteProtectedInAS>" in cx, "load-memory + write-protected emitted")
    ET.fromstring(cx); ET.fromstring(lx)                                            # both well-formed


def test_config_registry_from_shipped_csvs():
    # the 8 ex-signal_types DBs come from the shipped datablock_*.csv: the right ProgrammingLanguage, seeds
    # first, row-ordered members, the KQ pair both populated, and the ex-rule encoder member migrated to CSV 2.
    from pipeline3.domain import datablocks
    n_extra = {"index": "0001", "iol_FLD": "=S1+PC1-X1"}
    rows = [
        _db_row("E1/2", "Emergency Push Button [ =S1-S1 ]", "01_Pushbutton", "F_DB"),
        _db_row("DI1/2", "Door Closed SAFE_STATE [ =S1-B1 ]", "07_DOOR", "F_DB"),
        _db_row("DD", "Door Alarm [ =S1-B1 ]", "07_DOOR", "F_DB"),
        _db_row("KQ", "Contactor FB [ =S1-Q1 ]", "03_FDBACK|03_FDBACK_RAW", "F_DB"),
        {**_db_row("N1/2", "Safety Encoder 0001 Sensor 1 Healthy [ =S1+PC1-X1 ]", "04_SPEED", "F_DB"), **n_extra},
        _db_row("PA", "n0001 1.1.1.1", "PROFINET_NODES_ALARM", "DB"),
    ]
    g, _i, errs, _gw = datablocks.generate(
        rows, config.load_db_definitions(), config.load_db_elements(), config.load_db_types())
    eq(errs, [], "the shipped datablock_*.csv validate")
    eq(g["07_DOOR"]["prog_lang"], "F_DB", "07_DOOR is fail-safe")
    eq(g["PROFINET_NODES_ALARM"]["prog_lang"], "DB", "the alarm DB is normal")
    door = [m["name"] for m in g["07_DOOR"]["members"]]
    eq(door[:3], signals.DB_CONSTANTS, "seed constants first")
    ok("Door Closed SAFE_STATE [ =S1-B1 ]" in door and "Door Alarm [ =S1-B1 ]" in door, "DI + DD door members")
    for db in ("03_FDBACK", "03_FDBACK_RAW"):
        ok("Contactor FB [ =S1-Q1 ]" in [m["name"] for m in g[db]["members"]], f"KQ member -> {db}")
    spd = [m["name"] for m in g["04_SPEED"]["members"]]
    ok("Safety Encoder 0001 Sensor 1 Healthy [ =S1+PC1-X1 ]" in spd, "N1/2 name_in_db member")
    ok("Safety Encoder 0001 Healthy [ =S1+PC1-X1 ]" in spd, "the ex-datablock_elements_rules member, now CSV 2")


def test_fdb_opc_locked_regardless_of_config():
    # SAFETY FLOOR: a fail-safe DB is OPC-locked in CODE - an opc_ua=true (or a blank cell defaulting true)
    # cannot make it OPC-writable. A normal DB still follows opc_ua.
    fdb_true = signals._db_xml("S", {"prog_lang": "F_DB", "opc_ua": True, "members": []}, 1)
    ok("<DBAccessibleFromOPCUA>false</DBAccessibleFromOPCUA>" in fdb_true, "F_DB + opc_ua=true -> still OPC-locked")
    fdb_blank = signals._db_xml("S", {"prog_lang": "F_DB", "members": []}, 1)  # opc_ua key absent
    ok("<DBAccessibleFromOPCUA>false</DBAccessibleFromOPCUA>" in fdb_blank, "F_DB + no opc_ua -> OPC-locked")
    normal_off = signals._db_xml("N", {"prog_lang": "DB", "opc_ua": False, "members": []}, 1)
    ok("<DBAccessibleFromOPCUA>false</DBAccessibleFromOPCUA>" in normal_off, "DB + opc_ua=false -> OPC off")
    normal_on = signals._db_xml("N", {"prog_lang": "DB", "members": []}, 1)
    ok("<DBAccessibleFromOPCUA>true</DBAccessibleFromOPCUA>" in normal_on, "DB defaults OPC on")
    # the config loader also defaults a BLANK opc_ua to OFF for an F_DB (honest in-memory value) + warns on true
    from pipeline3.domain import datablocks
    _g, _i, _e, warns = datablocks.generate(
        [], [{"db_name": "X", "db_type": "Global", "db_programming_language": "F_DB",
              "for_each": "", "opc_ua": True}], [], [])
    ok(any("opc_ua=true ignored" in w for w in warns), "an explicit opc_ua=true on an F_DB is warned")


def test_constants_spelling():
    eq(signals.DB_CONSTANTS, ["Always FALSE", "Always TRUE", "No Operation"], "space, no underscore")
    from pipeline3.domain import datablocks
    eq(datablocks.DB_CONSTANTS, signals.DB_CONSTANTS, "the two DB_CONSTANTS copies must stay in lockstep")


def test_write_safe_db_xml():
    # a fail-safe DB is a GlobalDB XML carrying ProgrammingLanguage=F_DB + DBAccessibleFromOPCUA=false
    with tempfile.TemporaryDirectory() as d:
        dbs = {"07_DOOR": _db("F_DB", "Door Closed A", "Door Alarm [ =S1+SG1-B1 ]")}
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
        ok('<Member Name="Door Closed A"' in xtxt, "member emitted")
        ok('<Member Name="Always FALSE"' in xtxt and '<Member Name="Always TRUE"' in xtxt, "constants kept")
        ok('<Member Name="Door Alarm [ =S1+SG1-B1 ]"' in xtxt, "second member present")
        ok("<MemoryLayout>Optimized</MemoryLayout>" in xtxt)
        ok(xtxt.rstrip().endswith("</Document>"), "well-formed XML tail")
        ET.fromstring(xtxt)  # parses as valid XML


def test_write_normal_db_source():
    # a NORMAL DB is now ALSO a GlobalDB XML - it differs from F_DB only by ProgrammingLanguage=DB and
    # DBAccessibleFromOPCUA=true (OPC-UA accessible); the .db external source is gone.
    with tempfile.TemporaryDirectory() as d:
        dbs = {"PROFINET_NODES_ALARM": _db("DB", "Node X")}
        db_dir, count = signals.write_data_blocks(dbs, d)
        eq(count, 1)
        ok(os.path.exists(os.path.join(db_dir, "PROFINET_NODES_ALARM.xml")), "normal DB -> .xml too")
        ok(not os.path.exists(os.path.join(db_dir, "PROFINET_NODES_ALARM.db")), "no .db any more")
        raw = open(os.path.join(db_dir, "PROFINET_NODES_ALARM.xml"), "rb").read()
        ok(raw.startswith(b"\xef\xbb\xbf"), "UTF-8 BOM")
        ok(raw.count(b"\n") > 0 and raw.count(b"\n") == raw.count(b"\r\n"), "CRLF only")
        xtxt = raw.decode("utf-8-sig")
        ok("<ProgrammingLanguage>DB</ProgrammingLanguage>" in xtxt, "normal DB -> ProgrammingLanguage=DB")
        ok("<DBAccessibleFromOPCUA>true</DBAccessibleFromOPCUA>" in xtxt, "normal DB IS OPC-UA accessible")
        ok('<Member Name="Node X"' in xtxt, "member emitted")
        ok("SW.Blocks.GlobalDB" in xtxt, "still a GlobalDB block")
        ET.fromstring(xtxt)  # parses as valid XML


def test_write_clears_db_and_xml_not_scl():
    with tempfile.TemporaryDirectory() as d:
        dbs = {"PROFINET_NODES_ALARM": _db("DB", "Node X")}
        db_dir, _ = signals.write_data_blocks(dbs, d)
        scl = os.path.join(db_dir, "Diagnostic_for_OPC.scl"); open(scl, "w").write("keep me")
        stale_db = os.path.join(db_dir, "old.db"); open(stale_db, "w").write("x")
        stale_xml = os.path.join(db_dir, "old.xml"); open(stale_xml, "w").write("x")
        signals.write_data_blocks(dbs, d)
        ok(not os.path.exists(stale_db), "prior *.db swept")
        ok(not os.path.exists(stale_xml), "prior *.xml swept")
        ok(os.path.exists(scl), "the SCL (phase 620) is NOT swept")


def test_generate_data_blocks_from_registry():
    # the 520 entry drives off the config-driven registry (datablock_definitions/_elements/_types) - a DI1/2
    # row lands in the shipped 07_DOOR F_DB rule (member {name_in_db}); no datablock_elements_rules involved.
    with tempfile.TemporaryDirectory() as d:
        rows = [_db_row("DI1/2", "Door Closed", "07_DOOR", "F_DB", dev="-B1")]
        res = signals.generate_data_blocks(rows, d)
        eq(res["errors"], [])
        ok("07_DOOR" in res["dbs"]); ok("07_DOOR" in res["safe"])
        ok(res["count"] >= 1)
        ok(os.path.exists(os.path.join(res["dir"], "07_DOOR.xml")), "DB -> .xml")


def test_generate_data_blocks_halts_on_undeclared_db():
    # CSV 1 is authoritative: a signal naming a DB the registry doesn't declare HALTS 520 (writes nothing).
    with tempfile.TemporaryDirectory() as d:
        rows = [_db_row("DI1/2", "Door Closed", "07_DOOR|NOPE_DB", "F_DB", dev="-B1")]
        res = signals.generate_data_blocks(rows, d)
        ok(any("NOPE_DB" in e for e in res["errors"]), "undeclared DB flagged")
        ok(not any("07_DOOR" in e for e in res["errors"]), "the declared DB is not flagged")
        eq(res["count"], 0, "nothing written on a halt")
        ok(not os.path.exists(os.path.join(res["dir"], "NOPE_DB.xml")))
        ok(not os.path.exists(os.path.join(res["dir"], "07_DOOR.xml")))


def test_every_signal_db_name_is_declared():
    # no-false-positive guard: every db_name any signal type can emit IS declared as a Global in CSV 1, so the
    # undeclared-DB halt never fires on a real run (locks the invariant against future signal_types/CSV1 drift).
    sig_dbs = {n for t in config.load_signal_types().values() for n in (t.get("db_names") or []) if n}
    declared = {d["db_name"] for d in config.load_db_definitions()
                if (d.get("db_type") or "Global").strip().lower() == "global"}
    eq(sorted(sig_dbs - declared), [], "every signal_types db_name is declared in datablock_definitions.csv")


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
                    _db_row("DI1/2", "Door Closed", "07_DOOR", "F_DB", dev="-B1")]
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
        signals.write_data_blocks({"OTHER": {"prog_lang": "F_DB", "members": [{"name": "x", "comment": ""}]}}, d)
        ok(os.path.exists(com), "02_COM preserved through the 520 sweep")
        db_dir = config.out_path(d, "blocks_import_dir")
        other = os.path.join(db_dir, "OTHER.xml")
        ok(os.path.exists(other), "the 520-written DB present")
        x = open(other, encoding="utf-8-sig").read()
        ok("<ProgrammingLanguage>F_DB</ProgrammingLanguage>" in x
           and "<DBAccessibleFromOPCUA>false</DBAccessibleFromOPCUA>" in x,
           "prog_lang drives the fail-safe markers (a regression to normal would be caught here)")


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
        ("db_kind_of_alignment", test_db_kind_of_alignment),
        ("fdb_marker_canonicalized_and_unknown_warned", test_fdb_marker_canonicalized_and_unknown_warned),
        ("db_xml_config_attributes", test_db_xml_config_attributes),
        ("fdb_opc_locked_regardless_of_config", test_fdb_opc_locked_regardless_of_config),
        ("config_registry_from_shipped_csvs", test_config_registry_from_shipped_csvs),
        ("constants_spelling", test_constants_spelling),
        ("write_safe_db_xml", test_write_safe_db_xml),
        ("write_normal_db_source", test_write_normal_db_source),
        ("write_clears_db_and_xml_not_scl", test_write_clears_db_and_xml_not_scl),
        ("generate_data_blocks_from_registry", test_generate_data_blocks_from_registry),
        ("generate_data_blocks_halts_on_undeclared_db", test_generate_data_blocks_halts_on_undeclared_db),
        ("every_signal_db_name_is_declared", test_every_signal_db_name_is_declared),
        ("write_safe_db_xml_and_dedup", test_write_safe_db_xml_and_dedup),
        ("sweep_preserves_zone_cumulative_db", test_sweep_preserves_zone_cumulative_db),
        ("phase_registered", test_phase_registered),
        ("phase_run", test_phase_run),
    ]))
