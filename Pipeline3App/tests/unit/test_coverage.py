"""Data-independent unit cases for the Phase-910 coverage trace (domain/coverage.py).

The trace reads the ON-DISK output artifacts; the I/O (collect_outputs) is split from the pure
attribution (attribute), so the green gate stays hermetic: `attribute` is exercised with a synthetic
`outputs` (no disk), `find_unplaced` is pure, and the readers are checked once against a tiny
hand-written output tree in a temp dir. No real documents are needed.
"""
import os
import tempfile

from _harness import run, eq, ok
from pipeline3.domain import coverage
from pipeline3.core import config


def _sig(**kw):
    r = {"_type": {"type_id": "T1", "category": "Input"}, "script_type": "ZZ",
         "iol_FLD": "=S1+L-D", "name_in_db": "", "name_in_tagtable": "", "datablocks": "",
         "tagtable": "", "bit": "", "profinet_name": ""}
    r.update(kw)
    return r


def _outputs(**kw):
    base = {"tags": set(), "db_members": {}, "diag_bindings": set(), "iface_exprs": set(),
            "iface_instances": set(), "stations": set(), "sw_refs": {}, "consumed": [],
            "found": {s: True for s in coverage.STAGES}}
    base.update(kw)
    return base


# --- classification ----------------------------------------------------------------------- #
def test_is_signal_typed_or_identity():
    ok(coverage.is_signal(_sig()), "typed row is a signal")
    ok(coverage.is_signal({"_type": None, "name_in_tagtable": "Tag"}), "tagged row is a signal")
    ok(coverage.is_signal({"_type": None, "name_in_db": "M"}), "db-member row is a signal")
    ok(not coverage.is_signal({"_type": None, "bit": "I0.0"}), "untyped raw channel is not a signal")


def test_row_kind():
    eq(coverage.row_kind(_sig()), "signal")
    eq(coverage.row_kind({"_type": None, "bit": "I0.0"}), "channel")
    eq(coverage.row_kind({"_type": None, "bit": "Q4.1"}), "channel")
    eq(coverage.row_kind({"_type": None, "bit": ""}), "structural")


# --- attribution + ORPHAN ----------------------------------------------------------------- #
def test_orphan_is_only_a_signal_landing_nowhere():
    orphan = _sig(source_cell="S!A1")                            # typed, identity matches nothing
    tagged = _sig(source_cell="S!A2", name_in_tagtable="MyTag", tagtable="TT")
    channel = {"_type": None, "script_type": "", "bit": "I0.0", "source_cell": "S!A3"}
    out = _outputs(tags={"MyTag"})
    res = coverage.attribute([orphan, tagged, channel], out)
    flags = {r["source"]: r["flag"] for r in res["records"]}
    eq(flags["S!A1"], "ORPHAN", "typed signal with no output is ORPHAN")
    eq(flags["S!A2"], "", "tagged signal present in the tag table is not ORPHAN")
    eq(flags["S!A3"], "", "untyped raw channel is never ORPHAN")
    eq(res["stats"]["orphans"], 1)
    eq(res["stats"]["kinds"], {"signal": 2, "channel": 1, "structural": 0})


def test_placement_tags_blocks_diag_software():
    row = _sig(source_cell="S!B1", name_in_tagtable="Tag1", tagtable="TT1",
               name_in_db="Mem1", datablocks="DB_A")
    out = _outputs(tags={"Tag1"},
                   db_members={"DB_A": {"Mem1"}, "DB_B": {"Mem1"}},
                   diag_bindings={coverage.identity.plc_binding(row)},
                   sw_refs={"Mem1": {"05"}, "Tag1": {"08"}})
    rec = coverage.attribute([row], out)["records"][0]
    eq(rec["io_tags"], "TT1")
    eq(rec["data_blocks"], "DB_A|DB_B")           # member is in both generated DBs
    eq(rec["diagnosis"], "yes")
    eq(rec["software"], "05|08")
    ok(rec["outputs"] >= 4 and rec["flag"] == "")


def test_interface_defines_and_mirror():
    ioc = _sig(source_cell="S!C1", script_type="IOC", index="SORTER-01",
               _type={"type_id": "IOC", "category": "Interface"})
    mirrored = _sig(source_cell="S!C2", name_in_db="M", datablocks="DB")
    out = _outputs(iface_instances={"SORTER-01"},
                   iface_exprs={coverage.identity.plc_binding(mirrored)})
    res = coverage.attribute([ioc, mirrored], out)
    rec = {r["source"]: r for r in res["records"]}
    eq(rec["S!C1"]["interfaces"], "defines")
    eq(rec["S!C2"]["interfaces"], "mirror")


def test_hardware_station_and_module():
    head = _sig(source_cell="S!H1", _type={"type_id": "PA"}, profinet_name="nodeA",
                bit="", I_startByte=0, I_endByte=10)
    chan = {"_type": None, "script_type": "", "bit": "I5.0", "source_cell": "S!H2"}
    # chan resolves to nodeA's I byte range (diagnosis.node_of), which is a generated station
    out = _outputs(stations={"nodeA"})
    res = coverage.attribute([head, chan], out)
    rec = {r["source"]: r for r in res["records"]}
    eq(rec["S!H1"]["hardware"], "station")
    eq(rec["S!H2"]["hardware"], "module")


# --- UNPLACED ----------------------------------------------------------------------------- #
def test_find_unplaced_flags_dangling_generated_member_only():
    produced = {"DB_A": {"M1", "Always FALSE"}, "02_COM": {"AREA 9 PB"}}
    consumed = [
        ("diagnosis-SCL", "DB_A", "M1"),            # produced -> OK
        ("diagnosis-SCL", "DB_A", "M_missing"),      # generated DB, member absent -> UNPLACED
        ("interface-mirror", "DB_A", "M_missing"),   # same finding, second origin
        ("blk", "EXTERNAL_DB", "whatever"),          # not a generated DB -> ignored (920 scope)
    ]
    out = coverage.find_unplaced(produced, consumed)
    eq(len(out), 1)
    eq(out[0]["db"], "DB_A")
    eq(out[0]["member"], "M_missing")
    eq(out[0]["referenced_by"], "diagnosis-SCL|interface-mirror")


# --- readers (one pass over a tiny synthetic output tree) ---------------------------------- #
def test_readers_over_synthetic_tree():
    with tempfile.TemporaryDirectory() as root:
        # a normal .db + a safe GlobalDB .xml in ImportReady
        imp = config.out_path(root, "blocks_import_dir")
        os.makedirs(imp, exist_ok=True)
        with open(os.path.join(imp, "DB_N.db"), "w", encoding="utf-8-sig") as f:
            f.write('DATA_BLOCK "DB_N"\n   VAR \n      "M1" : Bool;\n      "M2" : Bool;\n   END_VAR\n')
        with open(os.path.join(imp, "DB_S.xml"), "w", encoding="utf-8-sig") as f:
            f.write('<SW.Blocks.GlobalDB><Member Name="S1" Datatype="Bool" /></SW.Blocks.GlobalDB>')
        with open(os.path.join(imp, "Diagnostic_for_OPC.scl"), "w", encoding="utf-8-sig") as f:
            f.write('IN_00 := "DB_N"."M1",\nIN_01 := "DB_N"."ghost",\n')
        # a CreationInfo CSV (the $/#/%/@ layout)
        cr = config.out_path(root, "blocks_creation_dir")
        os.makedirs(cr, exist_ok=True)
        with open(os.path.join(cr, "05_Output Feedback.csv"), "w", encoding="utf-8", newline="") as f:
            f.write("$,template=x\n#,gen\n%,TemplateType,!!a$$\n@,01,M2\n@,01,No Operation\n")
        # a Stations.csv (format-2)
        hw = config.out_path(root, "hardware_dir")
        os.makedirs(hw, exist_ok=True)
        with open(os.path.join(hw, "Stations.csv"), "w", encoding="utf-8", newline="") as f:
            f.write("#!format=2,,\n# Role,Station Name,Model\nPlc,nodeA,6ES7\n")

        out = coverage.collect_outputs(root)
        eq(out["db_members"]["DB_N"], {"M1", "M2"})
        eq(out["db_members"]["DB_S"], {"S1"})
        ok(("diagnosis-SCL", "DB_N", "ghost") in out["consumed"])
        eq(out["stations"], {"nodeA"})
        ok("M2" in out["sw_refs"] and out["sw_refs"]["M2"] == {"05"})
        ok("No Operation" not in out["sw_refs"], "pads are not software refs")
        eq(out["found"]["io_tags"], False)        # no PLCTags.xlsx written
        # the SCL ghost ref resolves to an UNPLACED finding
        up = coverage.find_unplaced(out["db_members"], out["consumed"])
        eq([(u["db"], u["member"]) for u in up], [("DB_N", "ghost")])


# --- rendering ---------------------------------------------------------------------------- #
def test_render_csv_and_txt():
    row = _sig(source_cell="S!D1", name_in_tagtable="Tag", tagtable="TT")
    res = coverage.attribute([row], _outputs(tags={"Tag"}))
    header, rows = coverage.render_csv(res)
    eq(header[0], "source")
    ok("flag" in header and "outputs" in header)
    eq(len(rows), 1)
    txt = coverage.render_txt(res)
    ok("PIPELINE COVERAGE REPORT" in txt and "ORPHAN" in txt and "UNPLACED" in txt)


if __name__ == "__main__":
    raise SystemExit(run("coverage", [
        ("is_signal_typed_or_identity", test_is_signal_typed_or_identity),
        ("row_kind", test_row_kind),
        ("orphan_is_only_a_signal_landing_nowhere", test_orphan_is_only_a_signal_landing_nowhere),
        ("placement_tags_blocks_diag_software", test_placement_tags_blocks_diag_software),
        ("interface_defines_and_mirror", test_interface_defines_and_mirror),
        ("hardware_station_and_module", test_hardware_station_and_module),
        ("find_unplaced_flags_dangling_generated_member_only", test_find_unplaced_flags_dangling_generated_member_only),
        ("readers_over_synthetic_tree", test_readers_over_synthetic_tree),
        ("render_csv_and_txt", test_render_csv_and_txt),
    ]))
