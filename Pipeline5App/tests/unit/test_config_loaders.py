"""Config-CSV loaders (core.config: read_config_csv / load_column_map / load_signal_types / resolve_type)."""
import os
import tempfile

from _harness import run, eq, ok
from pipeline5 import config


def test_read_config_csv_decodes_json_and_skips_blanks():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "c.csv")
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write('a,tags\r\nx,"[""one"",""two""]"\r\n,,\r\ny,\r\n')   # row 2 is all-empty (a trailing junk row)
        rows = config.read_config_csv(path, json_columns=["tags"])
        eq(len(rows), 2, "the all-empty row is skipped")
        eq(rows[0]["tags"], ["one", "two"], "a JSON-cell column decodes to a real list")
        eq(rows[1]["tags"], None, "an empty JSON cell -> None")
        eq(rows[1]["a"], "y", "a plain column stays a string")


def test_load_column_map_iolist():
    cols = config.load_column_map("IoList")
    ok(len(cols) >= 20, "the IoList column map loads")
    fu = next((c for c in cols if c["canonical"] == "functional_unit"), None)
    ok(fu is not None, "functional_unit is mapped")
    ok(isinstance(fu["required"], bool) and isinstance(fu["preliminary_check_exclude"], bool), "flags are bool")
    eq(config.load_column_map("nope"), [], "an unknown document -> []")


def test_load_signal_types_uses_the_stripped_schema():
    types = config.load_signal_types()
    ok("DI1/2" in types and "PA" in types, "types keyed by upper id")
    di = types["DI1/2"]
    for key in ("type_id", "category", "pair_key", "channel", "is_pattern", "tagtable_name", "tag_name",
                "io_comment", "ce_mandatory"):
        ok(key in di, f"{key} present")
    for gone in ("db_names", "db_element", "diag_desc", "in_diagnosis", "interface_tagname"):
        ok(gone not in di, f"the relocated column {gone} is gone")


def test_paired_channel_inherits_tagtable():
    types = config.load_signal_types()
    ok(types["E1/2"]["tagtable_name"], "E1/2 has a tagtable")
    eq(types["E2/2"]["tagtable_name"], types["E1/2"]["tagtable_name"],
       "the channel-2 type inherits its pair's tagtable_name")


def test_resolve_type_exact_and_pattern():
    types = config.load_signal_types()
    eq(config.resolve_type(types, "DI1/2")["type_id"], "DI1/2", "exact")
    eq(config.resolve_type(types, "di1/2")["type_id"], "DI1/2", "case-insensitive")
    z = config.resolve_type(types, "Z5")
    ok(z is not None and z["is_pattern"] and z["type_id"].startswith("Z"), "Z5 resolves to the Z# pattern type")
    eq(config.resolve_type(types, "NOPE"), None, "unknown -> None")
    eq(config.resolve_type(types, ""), None, "blank -> None")


def test_a_blank_line_before_the_header_is_skipped():
    """C-024 refute round 22's implications check: round 22 (F-C) fixed a blank FIRST line in reactions.csv only -
    the shared reader (`read_config_csv`, 14 config files) still read it as an EMPTY header and returned no
    rows, silently. Every config reader takes the first non-blank line as the header now."""
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "c.csv")
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write('\r\n  \r\n,,\r\na,tags\r\nx,"[""one""]"\r\ny,\r\n')
        rows = config.read_config_csv(path, json_columns=["tags"])
        eq([(row["a"], row["tags"]) for row in rows], [("x", ["one"]), ("y", None)], "the rows under a late header")
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write('\r\n,,\r\n')
        eq(config.read_config_csv(path), [], "blank lines only: no rows")


def _write(directory: str, name: str, text: str) -> str:
    path = os.path.join(directory, name)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    return path


def test_webui_builtin_files_load():
    """C-050: the safety system's webui/ files load through the tiers - the six v1 kinds (+ fire_alarm, off),
    each diag kind naming a real object family; the member patterns with their scopes; the strict params; the
    empty positions file; no drawing shipped."""
    kinds = config.load_webui_kinds()
    eq([k["kind"] for k in kinds if k["enabled"]], ["estop", "breaker", "door", "contactor", "encoder", "pn_node"])
    fire = next(k for k in kinds if k["kind"] == "fire_alarm")
    ok(not fire["enabled"] and fire["family"] == "fire_alarm", "a further kind is one row, switched off here")
    families = {r["family"] for r in config.read_config_csv(config.resolver.resolve("classification/object_families.csv"))}
    for kind in kinds:
        ok(kind["state"] == "node" or kind["family"] in families, f"{kind['kind']}: family {kind['family']!r} exists")
    eq(next(k for k in kinds if k["kind"] == "estop")["group_by"], ["functional_unit", "location"], "| lists split")
    states = config.load_webui_member_states()
    ok({s["scope"] for s in states} == {"area", "sorter", "node", "device"}, "every scope is used")
    q = next(s for s in states if s["member"] == "{area} Q")
    eq((q["db_name"], q["healthy"], q["role"]), ("05_EM_STATE", None, "state"), "blank healthy = unknown polarity")
    params = config.load_webui_params()
    eq((params["app"]["name"], params["polling"]["chunk"], params["login"]["users"]),
       ("safety", 50, ["Everybody", "Anonymous"]))
    eq(params["custom_data"]["db"], "PL5_CustomData")
    eq(config.load_webui_positions(params["layout"]["positions"]), [], "the shipped positions file is header only")
    eq(config.find_webui_drawing(params["layout"]["drawing"]), None, "no drawing ships with the system")


def test_webui_files_are_strict():
    """Config is config: a missing column / key / file is an error naming it, never a default; a bad cell names
    its row; a new kind row loads with no code change."""
    head = "kind,label,plural,icon,order,family,types,anchor_types,state,group_by,enabled,comment\r\n"
    with tempfile.TemporaryDirectory() as d:
        extra = _write(d, "k.csv", head + "estop,E-stop,E-stops,estop,10,emergency_pb,,,diag,location,yes,\r\n"
                                          "fire_alarm,Fire alarm,Fire alarms,fire,5,fire_alarm,F1/2,F1/2,diag,,yes,\r\n")
        eq([k["kind"] for k in config.load_webui_kinds(extra)], ["fire_alarm", "estop"], "sorted by order")
        eq(config.load_webui_kinds(extra)[0]["types"], ["F1/2"])
        for text, needle in ((head.replace("state,", ""), "state"),
                             (head + "estop,,,,10,,,,diag,,yes,\r\nestop,,,,20,,,,diag,,yes,\r\n", "appears twice"),
                             (head + "estop,,,,ten,,,,diag,,yes,\r\n", "order must be a whole number"),
                             (head + "estop,,,,10,,,,bits,,yes,\r\n", "state must be one of"),
                             (head + "estop,,,,10,,,,diag,,maybe,\r\n", "enabled must be yes or no")):
            path = _write(d, "bad.csv", text)
            try:
                config.load_webui_kinds(path)
                raise AssertionError(f"expected an error with {needle!r}")
            except ValueError as e:
                ok(needle in str(e), f"{needle!r} in {e}")
        mhead = "scope,db_name,member,label,healthy,severity,role,order,comment\r\n"
        good = _write(d, "m.csv", mhead + "area,05_EM_STATE,{area} Q,Q,true,alarm,state,1,\r\n")
        eq(config.load_webui_member_states(good)[0]["healthy"], True)
        for text, needle in ((mhead + "zone,05_EM_STATE,{area} Q,Q,,alarm,state,1,\r\n", "scope must be one of"),
                             (mhead + "area,05_EM_STATE,{area} Q,Q,yes,alarm,state,1,\r\n", "healthy must be"),
                             (mhead + "area,,{area} Q,Q,,alarm,state,1,\r\n", "db_name is empty")):
            try:
                config.load_webui_member_states(_write(d, "bad.csv", text))
                raise AssertionError(f"expected an error with {needle!r}")
            except ValueError as e:
                ok(needle in str(e), f"{needle!r} in {e}")
        shipped = open(config.resolver.resolve(config.WEBUI_PARAMS_REL), encoding="utf-8").read()
        for old, new, needle in (("  chunk: 50 ", "", "polling.chunk is missing"),
                                 ("custom_data:", "custom:", "the section 'custom_data' is missing"),
                                 ("name: safety ", "name: my app ", "app.name must be"),
                                 ("alarm_bit: null", "alarm_bit: 2", "diag.alarm_bit must be"),
                                 ("users: [Everybody, Anonymous]", "users: []", "login.users must be")):
            ok(old in shipped, f"the shipped params hold {old!r}")
            path = _write(d, "p.yaml", shipped.replace(old, new, 1))
            try:
                config.load_webui_params(path)
                raise AssertionError(f"expected an error with {needle!r}")
            except ValueError as e:
                ok(needle in str(e), f"{needle!r} in {e}")
        pos = _write(d, "pos.csv", "kind,fld,x,y\r\nestop,=ES-0035,10.5,20\r\n,,,\r\n")
        eq(config.load_webui_positions("pos.csv", pos), [{"kind": "estop", "fld": "=ES-0035", "x": 10.5, "y": 20.0}])
        try:
            config.load_webui_positions("pos.csv", _write(d, "pos.csv", "kind,fld,x,y\r\nestop,=E,left,1\r\n"))
            raise AssertionError("expected a number error")
        except ValueError as e:
            ok("x and y must be numbers" in str(e), str(e))


if __name__ == "__main__":
    import sys
    sys.exit(run("config_loaders", [
        ("webui_builtin_files_load", test_webui_builtin_files_load),
        ("webui_files_are_strict", test_webui_files_are_strict),
        ("read_config_csv_decodes_json_and_skips_blanks", test_read_config_csv_decodes_json_and_skips_blanks),
        ("a_blank_line_before_the_header_is_skipped", test_a_blank_line_before_the_header_is_skipped),
        ("load_column_map_iolist", test_load_column_map_iolist),
        ("load_signal_types_uses_the_stripped_schema", test_load_signal_types_uses_the_stripped_schema),
        ("paired_channel_inherits_tagtable", test_paired_channel_inherits_tagtable),
        ("resolve_type_exact_and_pattern", test_resolve_type_exact_and_pattern),
    ]))
