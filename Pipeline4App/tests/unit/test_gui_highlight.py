"""The Files-tab syntax highlighter (gui/highlight.py) - the Tk-free span tokenizer for YAML + JSON.
(The tag application on a Tk Text is a manual launch_gui check.)"""
from _harness import run, eq, ok
from pipeline4.gui import highlight


def _tags(kind, text):
    return [(tag, text[s:e]) for tag, s, e in highlight.spans(kind, text)]


def test_kind_of():
    eq(highlight.kind_of("a.yaml"), "yaml")
    eq(highlight.kind_of("B.YML"), "yaml")
    eq(highlight.kind_of("x.json"), "json")
    eq(highlight.kind_of("x.xml"), None, "only yaml/json highlight for now")


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


def test_unknown_kind_is_empty():
    eq(highlight.spans("xml", "<a>1</a>"), [], "unknown kinds produce no spans")


if __name__ == "__main__":
    import sys
    sys.exit(run("gui_highlight", [
        ("kind_of", test_kind_of),
        ("yaml_spans", test_yaml_spans),
        ("yaml_list_item_keys", test_yaml_list_item_keys),
        ("json_spans", test_json_spans),
        ("unknown_kind_is_empty", test_unknown_kind_is_empty),
    ]))
