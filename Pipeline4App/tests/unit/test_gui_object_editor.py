"""The Object-explorer MODEL (gui/object_editor.py, the Tk-free half): lossless yaml round-trip with a
scalar edit (comments/order survive), typed coercion, json round-trip, the path-role rules, and the
relative-keeping picker value. The Treeview/inline-entry UI is a manual launch_gui check."""
import json
import os
import tempfile

from _harness import run, eq, ok
from pipeline4.gui import object_editor as oe

_YAML = """\
# header comment stays
user_interface:
  language: en   # trailing comment stays
  font_size: 10
  dark: true
paths:
  iolist_path: docs/io.xlsx
"""


def test_yaml_edit_preserves_comments_and_types():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "t.yaml")
        with open(p, "w", encoding="utf-8", newline="") as h:
            h.write(_YAML)
        doc, kind = oe.load_document(p)
        eq(kind, "yaml")
        eq(oe.get_at(doc, ("user_interface", "font_size")), 10)
        oe.set_at(doc, ("user_interface", "font_size"), "12")
        oe.set_at(doc, ("user_interface", "dark"), "false")
        oe.set_at(doc, ("user_interface", "language"), "it")
        oe.dump_document(p, doc, kind)
        text = open(p, encoding="utf-8").read()
        ok("# header comment stays" in text, "the header comment survives the save")
        ok("# trailing comment stays" in text, "the trailing comment survives")
        doc2, _ = oe.load_document(p)
        eq(doc2["user_interface"]["font_size"], 12, "int stayed an int")
        eq(doc2["user_interface"]["dark"], False, "bool stayed a bool")
        eq(doc2["user_interface"]["language"], "it", "string edit landed")
        eq(list(doc2), ["user_interface", "paths"], "key order preserved")


def test_coerce_rules():
    eq(oe.coerce(10, " 42 "), 42, "int text -> int")
    eq(oe.coerce(10, "abc"), "abc", "unparsable stays a string")
    eq(oe.coerce(1.5, "2.25"), 2.25, "float text -> float")
    eq(oe.coerce(True, "no"), False, "bool words coerce (bool checked BEFORE int)")
    eq(oe.coerce(True, "maybe"), "maybe", "non-bool word stays a string")
    eq(oe.coerce("x", "7"), "7", "a string value stays a string even when numeric")


def test_json_round_trip():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "t.json")
        with open(p, "w", encoding="utf-8") as h:
            json.dump({"b": 1, "a": {"path": "x"}}, h)
        doc, kind = oe.load_document(p)
        eq(kind, "json")
        oe.set_at(doc, ("b",), "5")
        oe.dump_document(p, doc, kind)
        doc2 = json.load(open(p, encoding="utf-8"))
        eq(doc2["b"], 5, "typed edit")
        eq(list(doc2), ["b", "a"], "json key order preserved")


def test_path_role():
    eq(oe.path_role("iolist_path"), "file", "…path -> file picker")
    eq(oe.path_role("Path"), "file", "case-insensitive")
    eq(oe.path_role("output_dir"), "dir", "…dir -> directory picker")
    eq(oe.path_role("projects_root"), "dir", "…root -> directory picker")
    eq(oe.path_role("template_folder"), "dir", "…folder -> directory picker")
    eq(oe.path_role("language"), None, "a normal key gets no picker")


def test_picked_value_relative_keeping():
    with tempfile.TemporaryDirectory() as d:
        sub = os.path.join(d, "docs")
        os.makedirs(sub)
        chosen = os.path.join(sub, "io.xlsx")
        eq(oe.picked_value("docs/old.xlsx", chosen, d), "docs/io.xlsx",
           "a relative old value stays relative (/-separated)")
        eq(oe.picked_value(os.path.join(d, "abs.xlsx"), chosen, d), chosen,
           "an absolute old value stays absolute")
        outside = os.path.abspath(os.path.join(d, os.pardir, "other.xlsx"))
        eq(oe.picked_value("docs/old.xlsx", outside, d), outside,
           "a choice outside the base cannot stay relative")
        eq(oe.picked_value("", chosen, d), chosen, "an empty old value -> absolute")


def test_xml_load_and_items():
    """XML opens in the explorer as a READ-ONLY structure: attributes as @rows, non-blank text as
    #text, children in document order with [n] disambiguation for repeated tags."""
    import os
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "block.xml")
        with open(path, "w", encoding="utf-8") as h:
            h.write('<Doc Ver="1"><Member Name="A">x</Member><Member Name="B"/><Info/></Doc>')
        doc, kind = oe.load_document(path)
        eq(kind, "xml")
        ok(oe._is_element(doc) and doc.tag == "Doc")
        items = oe.xml_items(doc)
        eq(items[0], ("@Ver", "1"), "attributes come first as @rows")
        eq([k for k, _v in items[1:]], ["Member [1]", "Member [2]", "Info"],
           "repeated tags disambiguate; a unique tag stays bare")
        member = items[1][1]
        eq(oe.xml_items(member), [("@Name", "A"), ("#text", "x")], "text lands as #text")


if __name__ == "__main__":
    import sys
    sys.exit(run("gui_object_editor", [
        ("xml_load_and_items", test_xml_load_and_items),
        ("yaml_edit_preserves_comments_and_types", test_yaml_edit_preserves_comments_and_types),
        ("coerce_rules", test_coerce_rules),
        ("json_round_trip", test_json_round_trip),
        ("path_role", test_path_role),
        ("picked_value_relative_keeping", test_picked_value_relative_keeping),
    ]))
