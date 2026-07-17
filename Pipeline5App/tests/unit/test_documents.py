"""The Documents-tab config layer (`config.load_document_paths` / `save_document_path`): the round-trip
that the 4 input-document file pickers persist to project_params.yaml. Hermetic - runs against a temp
project so it never touches the real config; comments must survive the round-trip."""
import os
import tempfile

from _harness import run, eq, ok
from pipeline5 import config

_YAML = """\
project_code: "TST"

# the input documents (this comment must survive a save)
iolist_path: "C:/docs/io_current.xlsx"
iolist_previous_path: "C:/docs/io_prev.xlsx"
matrix_path: ""
matrix_previous_path: ""

matrix_params:
  sorter_areas: [1]
"""


def _with_temp_project(fn):
    root = tempfile.mkdtemp(prefix="pl4doc_")
    os.makedirs(os.path.join(root, "config_project", "shared"), exist_ok=True)
    with open(os.path.join(root, "config_project", "shared", "project_params.yaml"), "w", encoding="utf-8") as handle:
        handle.write(_YAML)
    try:
        config.use_project(root)
        fn(root)
    finally:
        config.use_builtin()


def test_load_document_paths():
    def body(_root):
        paths = config.load_document_paths()
        eq(set(paths), set(config.DOCUMENT_KEYS), "all 4 doc keys present")
        eq(paths["iolist_path"], "C:/docs/io_current.xlsx", "reads the stored current path")
        eq(paths["matrix_path"], "", "an empty path reads as ''")
    _with_temp_project(body)


def test_save_and_clear():
    def body(root):
        config.save_document_path("matrix_path", "C:/docs/ce_current.xlsx")
        eq(config.load_document_paths()["matrix_path"], "C:/docs/ce_current.xlsx", "a saved path round-trips")
        # the comment + the other params survive (round-trip mode)
        text = open(os.path.join(root, "config_project", "shared", "project_params.yaml"), encoding="utf-8").read()
        ok("this comment must survive" in text, "comments are preserved on save")
        ok("sorter_areas" in text, "unrelated params are preserved")
        eq(config.load_params()["project_code"], "TST", "the rest of the params still load")

        config.save_document_path("iolist_path", "")
        eq(config.load_document_paths()["iolist_path"], "", "clear stores an empty string")
    _with_temp_project(body)


def test_unknown_key_is_noop():
    def body(_root):
        before = config.load_document_paths()
        config.save_document_path("bogus_path", "x")        # not one of DOCUMENT_KEYS
        eq(config.load_document_paths(), before, "an unknown key writes nothing")
    _with_temp_project(body)


if __name__ == "__main__":
    import sys
    sys.exit(run("documents (config layer)", [
        ("load_document_paths", test_load_document_paths),
        ("save_and_clear", test_save_and_clear),
        ("unknown_key_is_noop", test_unknown_key_is_noop),
    ]))
