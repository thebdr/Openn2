"""Phase 900 (Coverage) - the row classification, the pure attribution (placement + ORPHAN/UNPLACED),
the SSOT-table reader collect_outputs, the renderers, and the build->project round-trip. Pure +
data-independent (the real-data parity is a separate script). Mirrors PL3's test_coverage.py, adapted to
PL4's SSOT model (reads the `type` cell + the stored `plc_binding`; collect_outputs reads tables, not disk)."""
import os
import tempfile

from _harness import run, eq, ok
from pipeline5.core import config
from pipeline5.core.ssot_database import Database as DB
from pipeline5.core.ssot_table import Table as CoreTable
from pipeline5.domain import signal_coverage as coverage


def _sig(**kw):
    r = {"source_cell": "S!1", "script_type": "", "name_in_db": "", "name_in_tagtable": "",
         "plc_binding": "", "bit": "", "profinet_name": "", "index": "", "tagtable": "",
         "iol_FLD": "", "type": None}
    r.update(kw)
    return r


def _outputs(**kw):
    o = {"tags": set(), "db_members": {}, "diag_bindings": set(), "iface_exprs": set(),
         "iface_instances": set(), "stations": set(), "sw_refs": {}, "consumed": [],
         "found": {s: True for s in coverage.STAGES}}
    o.update(kw)
    return o


# --- classification ---------------------------------------------------------------------------- #
def test_is_signal_and_row_kind():
    ok(coverage.is_signal(_sig(type={"type_id": "07_DOOR"})), "a resolved type -> signal")
    ok(coverage.is_signal(_sig(name_in_tagtable="X")), "a tag identity -> signal")
    ok(not coverage.is_signal(_sig(bit="I0.0")), "untyped, no identity -> not a signal")
    eq(coverage.row_kind(_sig(type={"type_id": "07_DOOR"})), "signal")
    eq(coverage.row_kind(_sig(bit="I3.2")), "channel", "untyped row with an I/Q address = a raw channel")
    eq(coverage.row_kind(_sig(bit="")), "structural", "untyped, no address = structural")


# --- attribution ------------------------------------------------------------------------------- #
def test_attribute_places_signal_across_stages():
    r = _sig(type={"type_id": "KQ"}, name_in_db="m1", name_in_tagtable="t1", tagtable="Alarms",
             plc_binding='"03_FDBACK"."m1"', script_type="KQ")
    out = _outputs(tags={"t1"}, db_members={"03_FDBACK": {"m1"}}, diag_bindings={'"03_FDBACK"."m1"'},
                   iface_exprs={'"03_FDBACK"."m1"'}, sw_refs={"m1": {"06"}})
    res = coverage.attribute([r], out)
    rec = res["records"][0]
    eq(rec["io_tags"], "Alarms", "io_tags cell = the tagtable")
    eq(rec["data_blocks"], "03_FDBACK", "the DB whose members contain name_in_db")
    eq(rec["diagnosis"], "yes")
    eq(rec["interfaces"], "mirror", "binding in an interface Expression")
    eq(rec["software"], "06")
    eq((rec["outputs"], rec["flag"]), (5, ""), "5 stages landed, not an ORPHAN")


def test_attribute_orphan_only_for_signals():
    rows = [_sig(source_cell="A", type={"type_id": "KQ"}, name_in_db="lonely"),   # signal, no output -> ORPHAN
            _sig(source_cell="B", bit="I2.0"),                                    # channel -> never ORPHAN
            _sig(source_cell="C")]                                                # structural -> never ORPHAN
    res = coverage.attribute(rows, _outputs())
    flags = {rec["source"]: rec["flag"] for rec in res["records"]}
    eq(flags, {"A": "ORPHAN", "B": "", "C": ""}, "only an unplaced signal is ORPHAN")
    eq(res["stats"]["orphans"], 1)
    eq(res["stats"]["kinds"], {"signal": 1, "channel": 1, "structural": 1})


def test_attribute_interface_defines_and_mirror():
    r = _sig(script_type="IOC", index="SORTER-01", plc_binding='"04_SPEED"."enc"', type={"type_id": "IOC"})
    res = coverage.attribute([r], _outputs(iface_instances={"SORTER-01"}, iface_exprs={'"04_SPEED"."enc"'}))
    eq(res["records"][0]["interfaces"], "defines|mirror", "an IOC row defines its interface AND mirrors")


def test_attribute_hardware_station_and_module():
    node = _sig(source_cell="N", profinet_name="n2", bit="", **{"type": {"type_id": "PA"}})
    node["I_startByte"], node["I_endByte"] = "0", "10"
    sigrow = _sig(source_cell="X", type={"type_id": "KI"}, name_in_db="k", bit="I5.0")
    head = _sig(source_cell="H", profinet_name="n1", type={"type_id": "PLC"})
    res = coverage.attribute([head, node, sigrow], _outputs(stations={"n1", "n2"}))
    by = {rec["source"]: rec["hardware"] for rec in res["records"]}
    eq(by["H"], "station", "a row whose own profinet_name is a station")
    eq(by["X"], "module", "a signal whose owning node (by address range) is a station")


def test_find_unplaced_dangling_member():
    produced = {"03_FDBACK": {"a"}}
    consumed = [("diagnosis", "03_FDBACK", "b"),       # generated DB, missing member -> UNPLACED
                ("diagnosis", "03_FDBACK", "a"),       # present -> ok
                ("interface-mirror", "05_EM_STATE", "x")]   # not a generated DB -> ignored (920 scope)
    up = coverage.find_unplaced(produced, consumed)
    eq(up, [{"db": "03_FDBACK", "member": "b", "referenced_by": "diagnosis"}])


# --- collect_outputs over the SSOT tables ------------------------------------------------------ #
def _ct(name, columns, json_columns, key_columns, rows):
    t = CoreTable(name, columns=["uid", *columns], json_columns=json_columns, key_columns=key_columns)
    for r in rows:
        t.add(**r)
    return t


def test_collect_outputs_from_tables():
    sig = _ct("signals",
              ["source_cell", "bit", "name_in_tagtable", "type"], ["type"], ["source_cell"],
              [{"source_cell": "S1", "bit": "I0.0", "name_in_tagtable": "TAG1",
                "type": {"type_id": "07_DOOR", "category": "Input"}},
               {"source_cell": "S2", "bit": "", "name_in_tagtable": "", "type": None}])
    dbm = _ct("db_members", ["db_name", "member"], [], ["db_name", "member"],
              [{"db_name": "07_DOOR", "member": "m1"}])
    de = _ct("diagnosis_entries", ["source", "in_binding", "diag_columns"], ["diag_columns"],
             ["source", "in_binding"],
             [{"source": "io", "in_binding": '"03_FDBACK"."x"', "diag_columns": {"PLC_Binding": '"03_FDBACK"."x"'}}])
    ie = _ct("interface_elements", ["interface", "signal_name", "expression"], [], ["interface", "expression"],
             [{"interface": "SORTER-01", "signal_name": "IFTAG", "expression": '"04_SPEED"."enc"'}])
    itab = _ct("interfaces", ["instance"], [], ["instance"], [{"instance": "SORTER-01"}])
    hs = _ct("hardware_stations", ["station_name"], [], ["station_name"], [{"station_name": "n1"}])
    hm = _ct("hardware_modules", ["station_name", "module_name"], [], ["station_name", "module_name"],
             [{"station_name": "n2", "module_name": "card1"}])
    blk = _ct("software_blocks", ["name", "columns"], ["columns"], ["name"],
              [{"name": "00_Only for Commissioning", "columns": ["TemplateType"]}])
    mem = _ct("software_block_members", ["block", "seq", "values"], ["values"], ["block", "seq"],
              [{"block": "00_Only for Commissioning", "seq": 0,
                "values": {"00_Commissioning.{db_element}": "n1 1.2.3.4", "02_COM.{db_element}": "AREA 1 PB"}}])
    db = DB([sig, dbm, de, ie, itab, hs, hm, blk, mem])
    o = coverage.collect_outputs(db)
    eq(o["tags"], {"TAG1", "IFTAG"}, "io-signal name_in_tagtable + interface_elements signal_name")
    eq(o["db_members"]["07_DOOR"], {"m1"})
    ok("02_COM" not in o["db_members"], "02_COM flows through db_members like any config DB now "
                                        "(this synthetic db_members has no 02_COM rows)")
    ok('"03_FDBACK"."x"' in o["diag_bindings"])
    eq(o["iface_exprs"], {'"04_SPEED"."enc"'})
    eq(o["iface_instances"], {"SORTER-01"})
    eq(o["stations"], {"n1", "n2"})
    eq(o["sw_refs"]["n1 1.2.3.4"], {"00"}, "software ref keyed by the block id (name before '_')")
    eq(o["sw_refs"]["AREA 1 PB"], {"00"})
    ok(("diagnosis", "03_FDBACK", "x") in o["consumed"])
    ok(("interface-mirror", "04_SPEED", "enc") in o["consumed"])
    ok(all(o["found"][s] for s in coverage.STAGES), "every stage table present + non-empty -> found")


# --- rendering + build/project ----------------------------------------------------------------- #
def test_render_csv_and_txt():
    res = coverage.attribute([_sig(source_cell="A", type={"type_id": "KQ"}, name_in_db="m")], _outputs())
    header, rows = coverage.render_csv(res)
    eq(header, coverage._CSV_COLUMNS, "the fixed CSV column order")
    eq(len(rows), 1)
    txt = coverage.render_txt(res)
    ok("PIPELINE COVERAGE REPORT" in txt and "ORPHAN" in txt and "UNPLACED" in txt, "the TXT sections")


def test_build_and_project_roundtrip():
    sig = _ct("signals", ["source_cell", "name_in_db", "type"], ["type"], ["source_cell"],
              [{"source_cell": "S1", "name_in_db": "m1", "type": {"type_id": "KQ"}}])    # ORPHAN (no outputs)
    with tempfile.TemporaryDirectory() as d:
        config.use_project(d)
        try:
            db = DB([sig])
            db, findings = coverage.build(db)
            eq(len(db["coverage"]), 1, "one coverage row persisted")
            eq(db["coverage"].rows[0]["flag"], "ORPHAN")
            eq([f.type for f in findings], ["cov_orphan_signal"], "the ORPHAN WARN finding")
            eq(findings[0].severity, "WARN")
            res = coverage.project(db, out_dir=d)
            ok(os.path.exists(res["csv"]) and os.path.exists(res["txt"]), "report files written")
            lines = open(res["csv"], encoding="utf-8").read().splitlines()
            eq(lines[0], ",".join(coverage._CSV_COLUMNS), "the CSV header")
            eq(res["stats"]["orphans"], 1)
        finally:
            config.use_builtin()


if __name__ == "__main__":
    import sys
    sys.exit(run("coverage", [
        ("is_signal_and_row_kind", test_is_signal_and_row_kind),
        ("attribute_places_signal_across_stages", test_attribute_places_signal_across_stages),
        ("attribute_orphan_only_for_signals", test_attribute_orphan_only_for_signals),
        ("attribute_interface_defines_and_mirror", test_attribute_interface_defines_and_mirror),
        ("attribute_hardware_station_and_module", test_attribute_hardware_station_and_module),
        ("find_unplaced_dangling_member", test_find_unplaced_dangling_member),
        ("collect_outputs_from_tables", test_collect_outputs_from_tables),
        ("render_csv_and_txt", test_render_csv_and_txt),
        ("build_and_project_roundtrip", test_build_and_project_roundtrip),
    ]))
