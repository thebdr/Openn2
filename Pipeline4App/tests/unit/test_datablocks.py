"""Phase 520 - domain.datablocks: the registry -> Global DBs / instance families + the write-back
(domain.db_members tables). Pure + data-independent (synthetic registry + rows)."""
from _harness import run, eq, ok
from pipeline4.domain import datablocks
from pipeline4.domain.db_members import db_members_table, instance_dbs_table


def _def(name, **kw):
    base = {"db_name": name, "db_type": "Global", "db_programming_language": "DB", "instance_of": "",
            "for_each": "", "memory_layout": "Optimized", "opc_ua": True, "webserver": True,
            "only_load_memory": False, "write_protected": False, "retain_reserve": False,
            "memory_reserve": "", "seed": False, "create_when": "if_elements", "comment": ""}
    base.update(kw)
    return base


def _el(db, member, for_each, **kw):
    base = {"db_name": db, "member": member, "for_each": for_each, "datatype": "Bool", "start_value": "",
            "retain": False, "ext_accessible": True, "ext_visible": True, "ext_writable": True,
            "setpoint": False, "comment": ""}
    base.update(kw)
    return base


_TYPES = [{"name": "Bool", "kind": "Elementary"}, {"name": "UDInt", "kind": "Elementary"}]
_ROWS = [
    {"uid": "u1", "script_type": "DI1/2", "combined_FLD": "S1-D1", "index": "1", "iol_FLD": "S1-D1"},
    {"uid": "u2", "script_type": "DI1/2", "combined_FLD": "S2-D2", "index": "2", "iol_FLD": "S2-D2"},
    {"uid": "u3", "script_type": "KQ", "combined_FLD": "S3-K3", "name_in_tagtable": "Feedback_S3"},
    {"uid": "u4", "script_type": "PA", "combined_FLD": "N1", "name_in_tagtable": "Node1"},
]


# --- generate: shells, seeds, the if_elements drop ----------------------------------------------- #
def test_generate_seeds_and_members():
    defs = [_def("07_DOOR", db_programming_language="F_DB", opc_ua=False, seed=True)]
    els = [_el("07_DOOR", "Door Closed [ {combined_FLD} ]", 'row where script_type = "DI1/2"')]
    g, inst, errors, warnings = datablocks.generate(_ROWS, defs, els, _TYPES)
    eq(errors, [], "a clean config -> no errors")
    names = [m["name"] for m in g["07_DOOR"]["members"]]
    eq(names, ["Always FALSE", "Always TRUE", "No Operation",
               "Door Closed [ S1-D1 ]", "Door Closed [ S2-D2 ]"], "seeds prepended, then a member per match")
    eq(g["07_DOOR"]["prog_lang"], "F_DB")


def test_generate_drops_seed_only_db():
    defs = [_def("EMPTY", seed=True)]                    # seeded but no element rows -> dropped (if_elements)
    g, _i, errors, _w = datablocks.generate(_ROWS, defs, [], _TYPES)
    eq(errors, [])
    ok("EMPTY" not in g, "a DB with only seeds (no real member) is dropped")


def test_generate_unique_instance_family():
    defs = [_def("S1.CAB{cabinet:03d}", db_type="Instance", instance_of="CabState",
                 for_each="cabinet in unique(diag_cabinet) where numeric(diag_cabinet)")]
    rows = [{"diag_cabinet": "1"}, {"diag_cabinet": "1"}, {"diag_cabinet": "2"}, {"diag_cabinet": ""}]
    _g, inst, errors, _w = datablocks.generate(rows, defs, [], _TYPES)
    eq(errors, [])
    eq(inst, [("S1.CAB001", "CabState"), ("S1.CAB002", "CabState")], "one instance per distinct numeric cabinet")


def test_generate_f_db_opc_warns():
    defs = [_def("SAFE", db_programming_language="F_DB", opc_ua=True, seed=True)]
    els = [_el("SAFE", "M [ {combined_FLD} ]", 'row where script_type = "DI1/2"')]
    _g, _i, errors, warnings = datablocks.generate(_ROWS, defs, els, _TYPES)
    eq(errors, [])
    ok(any("opc_ua=true ignored" in w for w in warnings), "opc_ua=true on an F_DB is warned")


def test_generate_member_dedup():
    defs = [_def("D", seed=False)]
    els = [_el("D", "M [ {combined_FLD} ]", 'row where script_type = "DI1/2"')]
    rows = [{"uid": "a", "script_type": "DI1/2", "combined_FLD": "X"},
            {"uid": "b", "script_type": "DI1/2", "combined_FLD": "X"}]   # same rendered name
    g, _i, errors, warnings = datablocks.generate(rows, defs, els, _TYPES)
    eq(errors, [])
    eq([m["name"] for m in g["D"]["members"]], ["M [ X ]"], "a duplicate member name is kept once")
    ok(any("more than once" in w for w in warnings), "the duplicate is warned")


# --- generate: validate-and-halt ----------------------------------------------------------------- #
def test_generate_validation_halts():
    # element names a DB the registry doesn't declare
    g, _i, errors, _w = datablocks.generate(_ROWS, [_def("KNOWN")], [_el("OTHER", "M", "")], _TYPES)
    eq(g, {}, "any error -> empty dbs (halt)")
    ok(any("not declared" in e for e in errors), "undeclared DB is an error")
    # unknown datatype
    _g, _i, errors, _w = datablocks.generate(_ROWS, [_def("D")], [_el("D", "M", "", datatype="Nope")], _TYPES)
    ok(any("unknown datatype" in e for e in errors))
    # only_load_memory + Optimized
    _g, _i, errors, _w = datablocks.generate(_ROWS, [_def("D", only_load_memory=True, memory_layout="Optimized")], [], _TYPES)
    ok(any("only_load_memory requires Standard" in e for e in errors))
    # bad for_each
    _g, _i, errors, _w = datablocks.generate(_ROWS, [_def("D")], [_el("D", "M", "row where @")], _TYPES)
    ok(any("for_each" in e for e in errors))


# --- write_back: name_in_db / datablocks / plc_binding ------------------------------------------- #
def test_write_back_single_db_and_tag_fallback():
    defs = [_def("07_DOOR", seed=True)]
    els = [_el("07_DOOR", "Door Closed [ {combined_FLD} ]", 'row where script_type = "DI1/2"')]
    rows = [dict(r) for r in _ROWS]
    g, _i, _e, _w = datablocks.generate(rows, defs, els, _TYPES)
    datablocks.write_back(rows, g)
    eq(rows[0]["name_in_db"], "Door Closed [ S1-D1 ]", "a DB member -> name_in_db")
    eq(rows[0]["datablocks"], ["07_DOOR"])
    eq(rows[0]["plc_binding"], '"07_DOOR"."Door Closed [ S1-D1 ]"')
    eq(rows[2]["name_in_db"], "", "a non-DB signal -> no name_in_db")
    eq(rows[2]["datablocks"], [])
    eq(rows[2]["plc_binding"], '"Feedback_S3"', "a non-DB signal binds to its tag")


def test_write_back_leftmost_db_order():
    # a PA signal joins ALARM then 00_Commissioning (element-row order) -> leftmost = ALARM
    defs = [_def("PROFINET_NODES_ALARM"), _def("00_Commissioning", db_programming_language="F_DB", seed=True)]
    els = [_el("PROFINET_NODES_ALARM", "{combined_FLD}", 'row where script_type = "PA"'),
           _el("00_Commissioning", "{combined_FLD}", 'row where script_type = "PA"')]
    rows = [dict(r) for r in _ROWS]
    g, _i, _e, _w = datablocks.generate(rows, defs, els, _TYPES)
    datablocks.write_back(rows, g)
    pa = rows[3]
    eq(pa["datablocks"], ["PROFINET_NODES_ALARM", "00_Commissioning"], "datablocks in element-row order")
    eq(pa["name_in_db"], "N1", "name_in_db is the member in the LEFTMOST DB")
    eq(pa["plc_binding"], '"PROFINET_NODES_ALARM"."N1"')


def test_write_back_two_members_one_db_picks_primary():
    # a single signal produces two members in one DB (the 04_SPEED case); the FIRST element row is primary
    defs = [_def("04_SPEED", db_programming_language="F_DB", seed=True)]
    els = [_el("04_SPEED", "Sensor 1 Healthy [ {iol_FLD} ]", 'row where script_type = "DI1/2"'),
           _el("04_SPEED", "Healthy [ {iol_FLD} ]", 'row where script_type = "DI1/2"')]
    rows = [dict(_ROWS[0])]
    g, _i, _e, _w = datablocks.generate(rows, defs, els, _TYPES)
    datablocks.write_back(rows, g)
    eq(rows[0]["name_in_db"], "Sensor 1 Healthy [ S1-D1 ]", "the earliest element row is the primary name_in_db")
    eq(rows[0]["datablocks"], ["04_SPEED"], "one DB even though two members")


# --- the SSOT tables ----------------------------------------------------------------------------- #
def test_fill_db_members_table_and_source():
    defs = [_def("07_DOOR", seed=True)]
    els = [_el("07_DOOR", "Door Closed [ {combined_FLD} ]", 'row where script_type = "DI1/2"')]
    rows = [dict(r) for r in _ROWS]
    g, _i, _e, _w = datablocks.generate(rows, defs, els, _TYPES)
    dbm = db_members_table()
    datablocks._fill_db_members(dbm, g)
    eq(len(dbm), 5, "3 seeds + 2 door members")
    seeds = [r for r in dbm if r["source"] == "seed"]
    eq(len(seeds), 3, "the seeds carry source='seed'")
    door = dbm.first(lambda r: r["member"] == "Door Closed [ S1-D1 ]")
    eq(door["source"], "u1", "a row-member's source is the producing signal's uid")
    eq(door["retain"], False, "the bool attrs are real bools (JSON cells)")
    eq(dbm.duplicate_uids(), set(), "every (db_name, member) hashes to a distinct uid")


def test_instance_dbs_table_keyed_by_name():
    idb = instance_dbs_table()
    idb.add(instance_name="S1.CAB001", fb="CabState")
    idb.add(instance_name="S1.CAB002", fb="CabState")
    eq(len(idb), 2)
    eq(idb.duplicate_uids(), set())


if __name__ == "__main__":
    import sys
    sys.exit(run("datablocks", [
        ("generate_seeds_and_members", test_generate_seeds_and_members),
        ("generate_drops_seed_only_db", test_generate_drops_seed_only_db),
        ("generate_unique_instance_family", test_generate_unique_instance_family),
        ("generate_f_db_opc_warns", test_generate_f_db_opc_warns),
        ("generate_member_dedup", test_generate_member_dedup),
        ("generate_validation_halts", test_generate_validation_halts),
        ("write_back_single_db_and_tag_fallback", test_write_back_single_db_and_tag_fallback),
        ("write_back_leftmost_db_order", test_write_back_leftmost_db_order),
        ("write_back_two_members_one_db_picks_primary", test_write_back_two_members_one_db_picks_primary),
        ("fill_db_members_table_and_source", test_fill_db_members_table_and_source),
        ("instance_dbs_table_keyed_by_name", test_instance_dbs_table_keyed_by_name),
    ]))
