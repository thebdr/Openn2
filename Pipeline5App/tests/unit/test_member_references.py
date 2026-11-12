"""Phase 800 - the undeclared-member check (phases/coverage/member_references.py, [[C-053]]): every Global-DB member a
generated block references - a ready FC XML's networks, a template-filled block's rows through their template
network, a ready SCL's assignments - must be one the generated DBs declare. A project whose own
datablock_members.csv is older than a builder's rename is the case it exists for: the block reads the new name, the
DB declares the old one, and TIA would only say so at compile time. Hermetic (in-memory tables) over the shipped
templates."""
import os

from _harness import run, eq, ok
from pipeline5.config import paths
from pipeline5.phases.coverage import member_references as mr
from pipeline5.phases.software_blocks import build_engine as engine
from pipeline5.phases.software_blocks.signals_view import Database
from pipeline5.systems.plc_based.siemens_s7 import fc_xml_emitter as xml_emit
from pipeline5.systems.plc_based.siemens_s7 import scl_emitter as scl_emit
from pipeline5.systems.plc_based.siemens_s7.safety import block_builders as builders
from pipeline5.systems.plc_based.siemens_s7.symbols import SYMBOLS
from pipeline5.truth.database import Database as DB
from pipeline5.truth.datablocks import db_blocks_table, db_members_table

ESTOP = os.path.join(paths.BLOCK_TEMPLATES_DIR, "TEMPLATE--v1.1--04_ESTOP.xml")
ZONE = os.path.join(paths.BLOCK_TEMPLATES_DIR, "TEMPLATE--v1.0--03_Zone Cumulative.xml")
AREA_1 = ["AREA 1 Q", "AREA 1 Q_Delayed", "AREA 1 RESET", "AREA 1 POWER ENABLED"]


def _db(members, dbs=("02_COM", "05_EM_STATE")) -> DB:
    """The generated DBs `dbs` with `members` = [(db, member) or (db, member, struct)], no block yet."""
    blocks, rows = db_blocks_table(), db_members_table()
    for name in dbs:
        blocks.add(db_name=name)
    for db_name, member, *struct in members:
        rows.add(db_name=db_name, member=member, struct=struct[0] if struct else "")
    return DB([blocks, rows, engine.software_blocks_table(), engine.software_block_members_table()])


def _block(database, name, template_ref, rows):
    """A template-filled block `name` whose @ rows are `rows` (value dicts), as engine.build stores it."""
    database["software_blocks"].add(name=name, template_stem=name, template_ref=template_ref, keys=[], columns=[])
    for seq, values in enumerate(rows):
        database["software_block_members"].add(block=name, seq=seq, values=values)


def _estop_row(pb="AREA 1 PB", fdb="AREA 1 FDB") -> dict:
    """04_ESTOP's bare-area network (TemplateType 02) for AREA 1, as build_04_estop writes it."""
    return {"TemplateType": "02", "NetworkComment": "AREA 1 ESTOP", "instanceOf-F_ESTOP1": "ESTOP_AREA 1",
            "02_COM.{matrix_area} PB": pb, "02_COM.{matrix_area} FDB": fdb,
            "02_COM.{matrix_area} DOORS": "", "02_COM.{matrix_area} SAFETY_BREAKERS": "",
            "05_EM_STATE.{matrix_area}_Q": "AREA 1 Q", "05_EM_STATE.{matrix_area}_Q_DELAYED": "AREA 1 Q_Delayed",
            "05_EM_STATE.{matrix_areas.1}_RESET": "AREA 1 RESET",
            "05_EM_STATE.{matrix_area}_POWER_CUT": "AREA 1 POWER ENABLED",
            "SPEED_STATE_REC.SORTER_{index}_ENCODER_HEALTHY": ""}


# --- the comparison -------------------------------------------------------------------------------- #
def test_only_generated_dbs_and_case_insensitive():
    """A reference into a generated DB must name a declared member - whatever its case (TIA's names are
    case-insensitive: the 02 template's `01_PushButton` is the DB `01_Pushbutton`); a tag, or a DB kept by hand on the
    TIA side (`SPEED_STATE_REC`), is none of PL5's to check. One finding per block place and symbol."""
    database = _db([("02_COM", "AREA 1 PB"), ("05_EM_STATE", "AREA 1 Q")])
    refs = [("04_ESTOP", "row 1", ("02_COM", "area 1 pb")),
            ("04_ESTOP", "row 1", ("02_com", "AREA 1 PB")),
            ("04_ESTOP", "row 1", ("02_COM", "AREA 1 E-STOP_PUSHBUTTONS")),
            ("04_ESTOP", "row 1", ("02_COM", "AREA 1 E-STOP_PUSHBUTTONS")),
            ("04_ESTOP", "row 2", ("02_COM", "AREA 1 E-STOP_PUSHBUTTONS")),
            ("04_ESTOP", "row 1", ("SPEED_STATE_REC", "SORTER_01_ENCODER_HEALTHY")),
            ("04_ESTOP", "row 1", ("SorterRunning",))]
    eq(mr.undeclared(database, refs),
       [("04_ESTOP", "row 1", '"02_COM"."AREA 1 E-STOP_PUSHBUTTONS"'),
        ("04_ESTOP", "row 2", '"02_COM"."AREA 1 E-STOP_PUSHBUTTONS"')], "the undeclared one, once per place")


def test_a_struct_member():
    """A member inside a Struct ([[C-042]]) is `"db"."struct"."member"`: a declared one passes, an undeclared one is
    named with its Struct, an unknown Struct by itself; a part past a plain member (an array index, a UDT's element)
    is not PL5's to check."""
    database = _db([("99_Commissioning", "RESET_VIA_TIA"), ("99_Commissioning", "n1 1.2.3.4", "NodesNotInstalled")],
                   dbs=("99_Commissioning",))
    refs = [("00", "row 2", ("99_Commissioning", "NodesNotInstalled", "n1 1.2.3.4")),
            ("00", "row 3", ("99_Commissioning", "NodesNotInstalled", "n2 1.2.3.5")),
            ("00", "row 4", ("99_Commissioning", "NodesInstalled", "n1 1.2.3.4")),
            ("00", "row 5", ("99_Commissioning", "RESET_VIA_TIA", "x"))]
    eq(mr.undeclared(database, refs),
       [("00", "row 3", '"99_Commissioning"."NodesNotInstalled"."n2 1.2.3.5"'),
        ("00", "row 4", '"99_Commissioning"."NodesInstalled"')])


# --- where the references come from ---------------------------------------------------------------- #
def test_a_stale_member_rule_fails_the_template_filled_block():
    """The stale-config case: the project's datablock_members.csv still declares AREA 1's push-button cumulative by an
    old name while 04_ESTOP's builder writes the new one - the row is read through the template's own network
    (TemplateType 02 of the shipped v1.1: a slot only another network wires, DOORS, is no reference), and the
    reference is a located blocking FAIL naming the symbol."""
    database = _db([("02_COM", "AREA 1 PUSHBUTTONS"), ("02_COM", "AREA 1 FDB")]
                   + [("05_EM_STATE", m) for m in AREA_1])
    _block(database, "04_ESTOP", ESTOP, [dict(_estop_row(), **{"02_COM.{matrix_area} DOORS": "AREA 1 DOORS"})])
    refs = mr.references(database)
    eq({p for _b, _w, p in refs}, {("02_COM", "AREA 1 PB"), ("02_COM", "AREA 1 FDB")}
       | {("05_EM_STATE", m) for m in AREA_1}, "exactly the TT02 network's symbols")
    findings = mr.check(database)
    eq([(f.phase, f.type, f.severity, f.location) for f in findings],
       [(800, "blk_undeclared_member", "FAIL", "04_ESTOP / row 1 (AREA 1 ESTOP)")], "one blocking finding")
    ok(findings[0].detail.startswith('references "02_COM"."AREA 1 PB", which DB 02_COM does not declare'),
       findings[0].detail)
    ok("datablock_members.csv" in findings[0].detail, "it names where the DB's members come from")
    eq([r["type"] for r in database["validation_issues"]], ["blk_undeclared_member"], "recorded")


def test_a_declared_block_passes():
    """The same row against the DB that declares what it reads: no finding, nothing recorded."""
    database = _db([("02_COM", "AREA 1 PB"), ("02_COM", "AREA 1 FDB")] + [("05_EM_STATE", m) for m in AREA_1])
    _block(database, "04_ESTOP", ESTOP, [_estop_row()])
    eq(mr.check(database), [])
    eq(list(database["validation_issues"]), [], "an empty record")


def test_an_untraceable_row_is_skipped():
    """A row whose template is missing, or whose TemplateType names no template network, has no wiring to read - the
    signal-paths report notes those; this check names nothing it cannot see."""
    database = _db([])
    _block(database, "04_ESTOP", ESTOP, [dict(_estop_row(), TemplateType="99")])
    _block(database, "09_Missing", os.path.join(paths.BLOCK_TEMPLATES_DIR, "none.xml"), [_estop_row()])
    eq(mr.references(database), [])


def test_the_ready_fc_xml_by_network():
    """A block PL5 renders READY (03 Zone Cumulative): every variable its rendered networks wire - the coil it writes
    and the members it ANDs - located by network and its title."""
    rows = [{"script_type": "E1/2", "matrix_areas": ["AREA 1"], "areas_description": ["Infeed"],
             "name_in_db": name, "datablocks": ["01_Pushbutton"]} for name in ("PB_A", "PB_B")]
    table = builders.build_03_zone_cumulative(Database(rows))
    xml = xml_emit.EMIT_FUNCS["fc_xml"](table, ZONE, "03_Zone Cumulative")
    database = _db([("01_Pushbutton", "PB_A"), ("02_COM", "AREA 1 PUSHBUTTONS")], dbs=("01_Pushbutton", "02_COM"))
    eq([(b, w) for b, w, _p in mr.references(database, ready_xml={"03_Zone Cumulative": xml})],
       [("03_Zone Cumulative", "network 1 (AREA 1 PB - Infeed)")] * 3, "the two inputs and the coil")
    eq(mr.undeclared(database, mr.references(database, ready_xml={"03_Zone Cumulative": xml})),
       [("03_Zone Cumulative", "network 1 (AREA 1 PB - Infeed)", '"01_Pushbutton"."PB_B"'),
        ("03_Zone Cumulative", "network 1 (AREA 1 PB - Infeed)", '"02_COM"."AREA 1 PB"')])


def test_the_ready_scl_by_region():
    """A block PL5 renders READY as SCL (03_Diagnostic Nodes): every `"db"."member"` it assigns, located by its REGION;
    the hand-kept `10_PN_NETWORK` it reads is not checked."""
    rows = [{"script_type": "PA", "profinet_name": "n1", "profinet_ip": "192.168.50.1"},
            {"script_type": "PW", "profinet_name": "sw1", "profinet_ip": "192.168.50.10"}]
    table = builders.build_03_diagnostic_nodes(Database(rows))
    scl = scl_emit.SCL_RENDERERS["03_Diagnostic Nodes"](table, "03_Diagnostic Nodes")
    database = _db([("PROFINET_NODES_ALARM", "n1 192.168.50.1")],
                   dbs=("PROFINET_NODES_ALARM", "PROFINET_NODES_WARNING", "10_PN_NETWORK"))
    eq(mr.undeclared(database, mr.references(database, ready_scl={"03_Diagnostic Nodes": scl},
                                             find_bindings=SYMBOLS.find_bindings)),
       [("03_Diagnostic Nodes", "REGION Subnet 50 192.168.50.xxx", '"PROFINET_NODES_WARNING"."sw1 192.168.50.10"')])


def test_a_ready_block_is_not_read_from_its_template():
    """A ready block's references come from what PL5 renders, never from its template's rows a second time."""
    database = _db([])
    _block(database, "04_ESTOP", ESTOP, [_estop_row()])
    eq(mr.references(database, ready_xml={"04_ESTOP": "<not xml/>"}), [])


if __name__ == "__main__":
    import sys
    sys.exit(run("member_references", [
        ("only_generated_dbs_and_case_insensitive", test_only_generated_dbs_and_case_insensitive),
        ("a_struct_member", test_a_struct_member),
        ("a_stale_member_rule_fails_the_template_filled_block", test_a_stale_member_rule_fails_the_template_filled_block),
        ("a_declared_block_passes", test_a_declared_block_passes),
        ("an_untraceable_row_is_skipped", test_an_untraceable_row_is_skipped),
        ("the_ready_fc_xml_by_network", test_the_ready_fc_xml_by_network),
        ("the_ready_scl_by_region", test_the_ready_scl_by_region),
        ("a_ready_block_is_not_read_from_its_template", test_a_ready_block_is_not_read_from_its_template),
    ]))
