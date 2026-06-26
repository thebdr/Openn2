"""Config-CSV loaders (core.config: read_config_csv / load_column_map / load_signal_types / resolve_type)."""
import os
import tempfile

from _harness import run, eq, ok
from pipeline4.core import config


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


if __name__ == "__main__":
    import sys
    sys.exit(run("config_loaders", [
        ("read_config_csv_decodes_json_and_skips_blanks", test_read_config_csv_decodes_json_and_skips_blanks),
        ("load_column_map_iolist", test_load_column_map_iolist),
        ("load_signal_types_uses_the_stripped_schema", test_load_signal_types_uses_the_stripped_schema),
        ("paired_channel_inherits_tagtable", test_paired_channel_inherits_tagtable),
        ("resolve_type_exact_and_pattern", test_resolve_type_exact_and_pattern),
    ]))
