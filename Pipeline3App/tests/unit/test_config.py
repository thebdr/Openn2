"""M1 gate: config layout, OUTPUT_PATHS contract, loaders."""
import os
from _harness import run, eq, ok
from pipeline3.core import config as c


def test_output_paths_keys():
    expected = {
        "validation_report", "validation_errors", "coverage_report", "run_log", "io_database",
        "diagnosis_dir", "interfaces_dir", "populated_iolist",
        "hardware_dir", "blocks_creation_dir", "blocks_import_dir", "io_tags_dir",
    }
    eq(set(c.OUTPUT_PATHS), expected, "OUTPUT_PATHS keys")


def test_open2app_surface_under_builderdata():
    # the confirmed import surface: every Open2App key lives under TiaPortalProjectInterface/BuilderData
    for key in c.OPEN2APP_KEYS:
        p = c.OUTPUT_PATHS[key]
        ok(os.path.join("TiaPortalProjectInterface", "BuilderData") in p, f"{key}: {p}")
    # and the documentation trees are NOT under BuilderData
    for key in ("validation_report", "io_database", "diagnosis_dir", "interfaces_dir"):
        ok("BuilderData" not in c.OUTPUT_PATHS[key], key)


def test_out_path_and_output_root():
    root = c.OUTPUT_ROOT
    eq(c.out_path(root, "io_tags_dir", "PLCTags.xlsx"),
       os.path.join(root, c.OUTPUT_PATHS["io_tags_dir"], "PLCTags.xlsx"))
    eq(c.output_root({}), c.OUTPUT_ROOT)
    eq(c.output_root({"output_dir": ""}), c.OUTPUT_ROOT)
    abs_dir = os.path.join(c.APP_ROOT, "X")
    eq(c.output_root({"output_dir": abs_dir}), abs_dir, "absolute output_dir wins")
    eq(c.output_root({"output_dir": "relative"}), c.OUTPUT_ROOT, "relative is ignored at output_root")


def test_anchors():
    ok(c.APP_ROOT.endswith("Pipeline3App"), c.APP_ROOT)
    ok(os.path.isdir(c.CONFIG_PROJECT))
    ok(os.path.isdir(c.INPUT_DOCS_DIR))


def test_helpers():
    eq(c.as_bool("yes"), True)
    eq(c.as_bool("NO"), False)
    eq(c.as_sheet_list("A"), ["A"])
    eq(c.as_sheet_list(["A", " B ", ""]), ["A", "B"])


def test_resolve_sheets():
    avail = ["NET SAFETY 50", "NET SAFETY NODES", "DiagnosisBlocks"]
    eq(c.resolve_sheets(["NET SAFETY 50"], avail), ["NET SAFETY 50"])
    eq(c.resolve_sheets([r"NET SAFETY \d+"], avail), ["NET SAFETY 50"])     # regex
    eq(c.resolve_sheet("DiagnosisBlocks", avail), "DiagnosisBlocks")
    eq(c.resolve_sheet("nope", avail), None)


def test_js_to_re():
    eq(c.js_to_re(r"NET SAFETY \d{1,3}/gmi"), r"NET SAFETY \d{1,3}")
    eq(c.js_to_re(r"/AREA\s?\d{1,2}/gmi"), r"AREA\s?\d{1,2}")
    eq(c.js_to_re(r"192.168.5\d"), r"192.168.5\d", "no trailing flags -> unchanged")
    eq(c.js_to_re("NET SAFETY 50"), "NET SAFETY 50", "plain name unchanged")
    eq(c.js_to_re("/foo/"), "foo", "bare /pattern/ wrapper")
    eq(c.js_to_re("AREA 1/2"), "AREA 1/2", "trailing /2 is not flags -> unchanged")


def test_resolve_sheets_js_literal():
    avail = ["COVER", "NET SAFETY 50", "NET SAFETY 100", "DiagnosisBlocks"]
    eq(c.resolve_sheets(r"NET SAFETY \d{1,3}/gmi", avail), ["NET SAFETY 50", "NET SAFETY 100"])


def test_load_params_builtin():
    p = c.load_params()                       # the built-in PARAMS_FILE
    ok("io_list" in p and "ce" in p)
    # builtin file leaves output_dir blank -> output_root falls back to OUTPUT_ROOT
    eq(c.output_root(p), c.OUTPUT_ROOT)
    # device_types_db/interface_template default to the Shared copies
    ok(p["device_types_db"].endswith("DeviceTypesDatabase.csv"))


def test_load_app_profile():
    import tempfile
    old = c.APP_CONFIG_FILE
    with tempfile.TemporaryDirectory() as d:
        try:
            p = os.path.join(d, "app_config.yaml")
            with open(p, "w", encoding="utf-8") as f:
                f.write("profile: designer\n")
            c.APP_CONFIG_FILE = p
            eq(c.load_app_profile(), "designer")
            with open(p, "w", encoding="utf-8") as f:
                f.write("profile: Bogus\n")
            eq(c.load_app_profile(), "bogus", "lenient: lowercased, validated by the GUI not here")
            c.APP_CONFIG_FILE = os.path.join(d, "absent.yaml")
            eq(c.load_app_profile(), "main", "missing file -> main")
        finally:
            c.APP_CONFIG_FILE = old


def test_profile_params_file():
    eq(c.profile_params_file("main"), c.PARAMS_FILE)
    eq(c.profile_params_file(None), c.PARAMS_FILE)
    eq(c.profile_params_file("designer"), c.DESIGNER_PARAMS_FILE, "designer -> designer_params.yaml")
    eq(c.profile_params_file("foo"), os.path.join(c.CONFIG_PROJECT, "foo_params.yaml"), "convention")


def test_load_signal_types():
    types = c.load_signal_types()
    ok(len(types) > 0)
    rec = next(iter(types.values()))
    for k in ("type_id", "category", "db_names", "in_diagnosis", "tag_name", "db_element"):
        ok(k in rec, k)
    ok(isinstance(rec["db_names"], list))


def test_load_rules_datablocks():
    rules = c.load_rules("datablock_elements_rules.csv")
    ok(isinstance(rules, list))
    if rules:
        r = rules[0]
        for k in ("name", "required_types", "db_name", "member"):
            ok(k in r, k)
        ok(isinstance(r["required_types"], list))


def test_load_device_types_db():
    db = c.load_device_types_db(c.load_params())
    ok("by_id" in db and "default_cards" in db)
    ok(len(db["by_id"]) > 0)


def test_column_map_interface_mapping():
    rows = c.load_column_map("IoList")
    by_can = {r["canonical"]: r["column"] for r in rows}
    eq(by_can["hardware_params"], "AG")
    eq(by_can["interface_mapping"], "AH", "interface_mapping at AH, not colliding with AG")
    cols = [r["column"] for r in rows]
    eq(len(cols), len(set(cols)), "no two IoList canonicals share a column letter")


def test_load_interface_elements_rules():
    rules = c.load_interface_elements_rules()
    ok(isinstance(rules, list) and len(rules) >= 1, "seed rules load")
    r = rules[0]
    for k in ("name", "required_types", "direction", "data_type", "script_type", "member"):
        ok(k in r, k)
    ok(r["direction"] in ("I", "Q")); ok(r["data_type"] in ("BOOL", "WORD"))
    ok(isinstance(r["required_types"], list))
    eq(c.INTERFACE_CUSTOM_GAP, 8)


if __name__ == "__main__":
    raise SystemExit(run("config", [
        ("output_paths_keys", test_output_paths_keys),
        ("open2app_surface_under_builderdata", test_open2app_surface_under_builderdata),
        ("out_path_and_output_root", test_out_path_and_output_root),
        ("anchors", test_anchors),
        ("helpers", test_helpers),
        ("resolve_sheets", test_resolve_sheets),
        ("js_to_re", test_js_to_re),
        ("resolve_sheets_js_literal", test_resolve_sheets_js_literal),
        ("load_params_builtin", test_load_params_builtin),
        ("load_app_profile", test_load_app_profile),
        ("profile_params_file", test_profile_params_file),
        ("load_signal_types", test_load_signal_types),
        ("load_rules_datablocks", test_load_rules_datablocks),
        ("load_device_types_db", test_load_device_types_db),
        ("column_map_interface_mapping", test_column_map_interface_mapping),
        ("load_interface_elements_rules", test_load_interface_elements_rules),
    ]))
