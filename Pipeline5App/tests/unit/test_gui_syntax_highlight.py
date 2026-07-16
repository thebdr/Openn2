"""The Files-tab syntax highlighter (gui/highlight.py) - the Tk-free span tokenizer for YAML + JSON.
(The tag application on a Tk Text is a manual launch_gui check.)"""
from _harness import run, eq, ok
from pipeline5.workbench import syntax_highlight as highlight


def _tags(kind, text):
    return [(tag, text[s:e]) for tag, s, e in highlight.spans(kind, text)]


def test_kind_of():
    eq(highlight.kind_of("a.yaml"), "yaml")
    eq(highlight.kind_of("B.YML"), "yaml")
    eq(highlight.kind_of("x.json"), "json")
    eq(highlight.kind_of("x.xml"), "xml", "xml highlights too (production-test request)")
    eq(highlight.kind_of("x.scl"), "scl", "scl is a data-driven language now (langs.json)")
    eq(highlight.kind_of("x.log"), None, "an unmapped text kind stays plain")


def test_yaml_spans():
    text = ("# top comment\n"
            "user_interface:\n"
            "  language: en   # trailing\n"
            "  font_size: 10\n"
            "  dark: true\n"
            "  title: \"a # not a comment\"\n"
            "  items: ['a', 'b']\n")
    got = _tags("yaml", text)
    ok(("hl_cmt", "# top comment") in got, "full-line comment")
    ok(("hl_cmt", "# trailing") in got, "trailing comment")
    ok(("hl_key", "user_interface") in got, "top-level key")
    ok(("hl_key", "  language") in got, "nested key (leading indent included)")
    ok(("hl_num", "10") in got, "number value")
    ok(("hl_bool", "true") in got, "boolean value")
    ok(("hl_str", '"a # not a comment"') in got, "a # inside a quoted string stays a string")
    ok(not any(t == "hl_cmt" and "not a comment" in s for t, s in got), "no comment inside the string")


def test_yaml_list_item_keys():
    text = ("sections:\n"
            "  - title: Project configuration\n"
            "    roots: [\"${config_project}\"]\n")
    got = _tags("yaml", text)
    ok(("hl_key", "sections") in got, "parent key")
    ok(any(t == "hl_key" and s.strip().endswith("title") for t, s in got), "a '- key:' item key")


def test_json_spans():
    text = '{"name": "PL4", "count": 3, "ok": true, "rate": -1.5e2, "note": null}'
    got = _tags("json", text)
    eq([s for t, s in got if t == "hl_key"], ['"name"', '"count"', '"ok"', '"rate"', '"note"'],
       "a string before ':' is a key")
    ok(("hl_str", '"PL4"') in got, "a value string stays a string")
    ok(("hl_num", "3") in got and ("hl_num", "-1.5e2") in got, "ints + scientific floats")
    ok(("hl_bool", "true") in got and ("hl_bool", "null") in got, "true/null")


def test_xml_spans():
    text = ('<?xml version="1.0"?>\n<Root Id="7">\n  <!-- note -->\n'
            '  <Name>DB_1</Name>\n</Root>')
    got = [(tag, text[s:e]) for tag, s, e in highlight.spans("xml", text)]
    ok(("hl_key", "<Root") in got and ("hl_key", "</Name") in got, "tag names")
    ok(("hl_key", "<?xml") in got, "the declaration")
    ok(("hl_bool", "Id") in got and ("hl_bool", "version") in got, "attribute names")
    ok(("hl_str", '"7"') in got and ("hl_str", '"1.0"') in got, "attribute values")
    ok(("hl_cmt", "<!-- note -->") in got, "comments")
    ok(not any(t == "hl_bool" and v == "Name" for t, v in got), "a tag is not an attribute")


def test_data_driven_languages():
    """The Notepad++-UDL-style langs.json tier: scl/sql/ini ship as PLAIN DATA compiled into the
    same span engine; extensions route kind_of; only yaml/json/xml carry the Object view."""
    ok({"scl", "sql", "ini"} <= set(highlight.LANGS), "the shipped languages loaded")
    eq(highlight.kind_of("Diagnostic for OPC.scl"), "scl")
    eq(highlight.kind_of("q.SQL"), "sql")
    eq(highlight.object_kind_of("a.scl"), None, "a data language has NO object view")
    eq(highlight.object_kind_of("a.yaml"), "yaml", "the structured kinds keep theirs")
    ok(set(("yaml", "json", "xml")) <= set(highlight.available_kinds()), "the picker lists all kinds")
    scl = "// note\nIF NOT #x THEN\n  y := 16#FF;\n  s := 'it''s';\nEND_IF;"
    got = [(tag, scl[a:b]) for tag, a, b in highlight.spans("scl", scl)]
    ok(("hl_cmt", "// note") in got, "scl line comment")
    ok(("hl_key", "IF") in got and ("hl_key", "END_IF") in got and ("hl_key", "NOT") in got,
       "scl keywords (case-insensitive)")
    ok(("hl_num", "16#FF") in got, "the scl hex literal beats the plain number rule")
    ok(any(tag == "hl_str" for tag, _v in got), "scl strings")


def test_unknown_kind_is_empty():
    eq(highlight.spans("toml", "a = 1"), [], "unknown kinds produce no spans")


if __name__ == "__main__":
    import sys
    sys.exit(run("gui_highlight", [
        ("kind_of", test_kind_of),
        ("yaml_spans", test_yaml_spans),
        ("yaml_list_item_keys", test_yaml_list_item_keys),
        ("json_spans", test_json_spans),
        ("xml_spans", test_xml_spans),
        ("data_driven_languages", test_data_driven_languages),
        ("unknown_kind_is_empty", test_unknown_kind_is_empty),
    ]))
