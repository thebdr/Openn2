"""Gate (data-independent): the config-driven DB engine (domain/datablocks.py).

generate() validates the 3-CSV config (unknown type / undeclared DB / bad template / optimized+load-memory
⇒ errors) and produces the Global DBs (members + attrs) + the Instance-DB families. The DiagnosticTags shape
is exercised end-to-end over synthetic cabinets.
"""
from _harness import run, eq, ok

from pipeline3.domain import datablocks as DB

_TYPES = [{"name": "Bool", "kind": "Elementary"}, {"name": "UDInt", "kind": "Elementary"}]
_FE = 'cabinet in unique(diag_cabinet) where numeric(diag_cabinet)'


def _gdef(**kw):
    d = {"db_name": "", "db_type": "Global", "db_programming_language": "DB", "instance_of": "",
         "for_each": "", "memory_layout": "Optimized", "opc_ua": True, "webserver": True,
         "only_load_memory": False, "write_protected": False, "retain_reserve": False,
         "memory_reserve": "", "create_when": "if_elements", "comment": ""}
    d.update(kw)
    return d


def _elem(**kw):
    e = {"db_name": "DiagnosticTags", "member": "", "for_each": _FE, "datatype": "UDInt", "start_value": "",
         "retain": False, "ext_accessible": True, "ext_visible": True, "ext_writable": True,
         "setpoint": False, "comment": ""}
    e.update(kw)
    return e


def _diag_defs():
    defs = [_gdef(db_name="DiagnosticTags")]
    for role, fb in (("STATE", "CabState"), ("ALARM1", "BoolToUDInt"), ("ALARM2", "BoolToUDInt"),
                     ("WARNING1", "BoolToUDInt"), ("WARNING2", "BoolToUDInt")):
        defs.append(_gdef(db_name="S1.CABINET{cabinet:03d}." + role, db_type="Instance",
                          instance_of=fb, for_each=_FE, create_when="always"))
    return defs


def _diag_elems():
    return [_elem(member="S1.CABINET{cabinet:03d}." + r) for r in ("STATE", "ALARM1", "ALARM2", "WARNING1", "WARNING2")]


def _rows():
    return [{"diag_cabinet": "1", "x": "a"}, {"diag_cabinet": "2"}, {"diag_cabinet": "-1"},
            {"diag_cabinet": ""}, {"diag_cabinet": "1"}]


def test_diagnostictags_end_to_end():
    g, inst, errs, warns = DB.generate(_rows(), _diag_defs(), _diag_elems(), _TYPES)
    eq(errs, [], "no validation errors")
    ok("DiagnosticTags" in g, "the Global DB created")
    mem = g["DiagnosticTags"]["members"]
    names = [m["name"] for m in mem]
    eq(len(names), 10, "2 numeric cabinets x 5 roles")
    ok("S1.CABINET001.STATE" in names and "S1.CABINET002.WARNING2" in names, "padded per-cabinet names")
    ok(all(m["datatype"] == "UDInt" for m in mem), "members are UDInt")
    eq(g["DiagnosticTags"]["prog_lang"], "DB")
    # instance families: 10 (name, fb), STATE->CabState else BoolToUDInt
    eq(len(inst), 10, "5 roles x 2 cabinets")
    by = dict(inst)
    eq(by["S1.CABINET001.STATE"], "CabState")
    eq(by["S1.CABINET002.ALARM1"], "BoolToUDInt")


def test_validation_collects_and_halts():
    # unknown datatype
    g, i, errs, w = DB.generate(_rows(), _diag_defs(), [_elem(member="X{cabinet}", datatype="Nope")], _TYPES)
    ok(any("unknown datatype" in e for e in errs), "unknown type halts")
    eq(g, {}, "no DBs returned on error")
    # member's DB not declared
    _, _, errs2, _ = DB.generate(_rows(), _diag_defs(), [_elem(db_name="Ghost", member="m")], _TYPES)
    ok(any("not declared" in e for e in errs2), "undeclared DB halts")
    # only_load_memory + Optimized
    _, _, errs3, _ = DB.generate(_rows(), [_gdef(db_name="D", only_load_memory=True, memory_layout="Optimized")],
                                 [], _TYPES)
    ok(any("only_load_memory requires Standard" in e for e in errs3), "load-memory/optimized clash halts")
    # bad for_each
    _, _, errs4, _ = DB.generate(_rows(), [_gdef(db_name="D", for_each="cabinet in unique(")], [], _TYPES)
    ok(errs4, "a for_each syntax error halts")
    # an unknown column WARNS (yields nothing) - it does not halt (a partial row set may omit a column)
    _, _, errs5, warns5 = DB.generate(_rows(), _diag_defs(), [_elem(member="m{c}", for_each="c in unique(nope)")], _TYPES)
    eq(errs5, [], "an unknown column does not halt")
    ok(any("present in no row" in w for w in warns5), "unknown column -> warning")


def test_create_when_and_dedup():
    # if_elements: a Global with no surviving members is dropped
    g, _, errs, _ = DB.generate([{"diag_cabinet": ""}], _diag_defs(), _diag_elems(), _TYPES)
    eq(errs, [])
    ok("DiagnosticTags" not in g, "no numeric cabinets -> if_elements drops the empty DB")
    # always: kept even when empty
    g2, _, _, _ = DB.generate([{"diag_cabinet": ""}], [_gdef(db_name="Keep", create_when="always")], [], _TYPES)
    ok("Keep" in g2 and g2["Keep"]["members"] == [], "create_when=always keeps an empty DB")
    # dedup: duplicate member name collapses + warns
    rows = [{"diag_cabinet": "1"}, {"diag_cabinet": "1"}]
    g3, _, _, warns = DB.generate(rows, [_gdef(db_name="D", create_when="always")],
                                  [_elem(db_name="D", member="FIXED", for_each="c in unique(diag_cabinet)")], _TYPES)
    eq([m["name"] for m in g3["D"]["members"]], ["FIXED"], "same rendered name kept once")


def test_per_row_and_attrs():
    # blank for_each on an element = one literal member; member attrs flow through
    g, _, errs, _ = DB.generate([], [_gdef(db_name="D", create_when="always")],
                                [_elem(db_name="D", member="Always FALSE", for_each="", datatype="Bool",
                                       start_value="False", retain=True, setpoint=True, ext_writable=False)], _TYPES)
    eq(errs, [])
    m = g["D"]["members"][0]
    eq((m["name"], m["datatype"], m["retain"], m["start_value"], m["setpoint"], m["ext_writable"]),
       ("Always FALSE", "Bool", True, "False", True, False), "member attributes carried")
    # per_row over rows
    rows = [{"script_type": "DI1/2", "iol_FLD": "=S1+A"}, {"script_type": "KQ"}]
    g2, _, _, _ = DB.generate(rows, [_gdef(db_name="DOOR", create_when="always")],
                              [_elem(db_name="DOOR", member="Door [ {iol_FLD} ]", datatype="Bool",
                                     for_each='row where script_type in ["DI1/2"]')], _TYPES)
    eq([m["name"] for m in g2["DOOR"]["members"]], ["Door [ =S1+A ]"], "per-row filtered member")


if __name__ == "__main__":
    raise SystemExit(run("datablocks", [
        ("diagnostictags_end_to_end", test_diagnostictags_end_to_end),
        ("validation_collects_and_halts", test_validation_collects_and_halts),
        ("create_when_and_dedup", test_create_when_and_dedup),
        ("per_row_and_attrs", test_per_row_and_attrs),
    ]))
