"""M11 polish: the object editor's pure structural mutations (Tk-free).

The Tk widgets need a display, but objedit's add/delete helpers, _coerce, and the path-hint are plain
data ops - so test those + the ruamel comment-preservation promise headlessly (importing objedit does
not create a Tk root)."""
import io
import xml.etree.ElementTree as ET

from _harness import run, ok, eq
from pipeline3.gui import objedit


def test_add_and_delete_dict_list():
    d = {"a": 1, "b": 2}
    objedit.add_key(d, "c")
    eq(d["c"], "", "add_key inserts an empty scalar")
    raised = False
    try:
        objedit.add_key(d, "a")
    except KeyError:
        raised = True
    ok(raised, "add_key rejects a duplicate")
    objedit.delete_node(d, "a", "scalar")
    ok("a" not in d, "delete_node removes a dict key")
    seq = [10, 20]
    objedit.add_item(seq)
    eq(seq[-1], "", "add_item appends an empty scalar")
    objedit.delete_node(seq, 0, "scalar")
    eq(seq, [20, ""], "delete_node removes a list index")


def test_delete_xml():
    root = ET.fromstring("<root a='1'><child/></root>")
    child = list(root)[0]
    objedit.delete_node(root, None, "xml_elem", child)
    eq(len(list(root)), 0, "xml element removed")
    objedit.delete_node(root, "a", "xml_attr")
    ok("a" not in root.attrib, "xml attribute removed")


def test_yaml_comments_survive_add_delete():
    from ruamel.yaml import YAML
    y = YAML()
    y.preserve_quotes = True
    y.width = 4096
    src = "# header comment\nio_list:\n  path: old.xlsx   # the source\n  fuzzy: 2\nkeep: true\n"
    data = y.load(src)
    objedit.add_key(data["io_list"], "note")
    objedit.delete_node(data["io_list"], "fuzzy", "scalar")
    s = io.StringIO()
    y.dump(data, s)
    out = s.getvalue()
    ok("# header comment" in out, "the top comment survives the add+delete")
    ok("# the source" in out, "the inline comment survives")
    ok("note:" in out, "the added key is present")
    ok("fuzzy:" not in out, "the deleted key is gone")


def test_coerce_type_preserved():
    eq(objedit._coerce("42", 0), 42, "int kept")
    eq(objedit._coerce("3.5", 0.0), 3.5, "float kept")
    eq(objedit._coerce("false", True), False, "bool kept")
    eq(objedit._coerce("C:/x.xlsx", ""), "C:/x.xlsx", "a string (e.g. a browsed path) stays a string")


def test_key_wants_dir():
    ok(objedit._key_wants_dir("output_dir"), "a *dir key offers the folder picker first")
    ok(objedit._key_wants_dir("Templates folder"))
    ok(not objedit._key_wants_dir("path"), "a plain path leaf defaults to the file picker")


if __name__ == "__main__":
    raise SystemExit(run("objedit", [
        ("add_and_delete_dict_list", test_add_and_delete_dict_list),
        ("delete_xml", test_delete_xml),
        ("yaml_comments_survive_add_delete", test_yaml_comments_survive_add_delete),
        ("coerce_type_preserved", test_coerce_type_preserved),
        ("key_wants_dir", test_key_wants_dir),
    ]))
