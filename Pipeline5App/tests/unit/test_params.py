"""The nested project-params loader (core.config.load_params / get_param)."""
import os
import tempfile

from _harness import run, eq, ok
from pipeline5 import config

_YAML = """project_code: "8XXX"
iolist_path: "docs/io.xlsx"
matrix_path: "C:/abs/matrix.xlsx"
iolist_params:
  sheets: "NET SAFETY 50"
  diag_bits_range: [0, 62]
matrix_params:
  sorter_areas: [1]
  ce_sheet:
    name: "CAUSE&EFFECT MATRIX"
    header_row: 2
validation_params:
  global:
    strike_handling: "exclude"
    print_all: false
  crosscheck:
    iol_in_matrix:
      mandatory_words: ["emergency", "safety"]
      levenshtein_deviation: 1
"""


def _write(directory):
    path = os.path.join(directory, "project_params.yaml")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(_YAML)
    return path


def test_load_resolves_document_paths():
    with tempfile.TemporaryDirectory() as d:
        params = config.load_params(_write(d))
        eq(params["iolist_path"], os.path.normpath(os.path.join(d, "docs", "io.xlsx")),
           "a relative document path is resolved to absolute, from the params dir")
        eq(params["matrix_path"], "C:/abs/matrix.xlsx", "an absolute path is left unchanged")
        eq(params["project_code"], "8XXX")


def test_get_param_reads_nested_values():
    with tempfile.TemporaryDirectory() as d:
        params = config.load_params(_write(d))
        eq(config.get_param(params, "validation_params.crosscheck.iol_in_matrix.mandatory_words"),
           ["emergency", "safety"], "deep nested list")
        eq(config.get_param(params, "validation_params.crosscheck.iol_in_matrix.levenshtein_deviation"), 1)
        eq(config.get_param(params, "matrix_params.sorter_areas"), [1])
        eq(config.get_param(params, "iolist_params.diag_bits_range"), [0, 62])
        eq(config.get_param(params, "validation_params.global.print_all", True), False,
           "a present False is returned, NOT the default")


def test_get_param_missing_returns_default():
    with tempfile.TemporaryDirectory() as d:
        params = config.load_params(_write(d))
        eq(config.get_param(params, "validation_params.nope.x", "DFLT"), "DFLT", "missing middle -> default")
        eq(config.get_param(params, "iolist_params.sheets.deep", 7), 7, "descending into a scalar -> default")
        eq(config.get_param(params, "totally.absent"), None, "default is None when unspecified")


def test_shipped_project_params_loads():
    # the builtin config_project/project_params.yaml parses + carries the adopted nested blocks
    params = config.load_params()
    eq(config.get_param(params, "matrix_params.ce_sheet.name"), "CAUSE&EFFECT MATRIX")
    ok(config.get_param(params, "validation_params.crosscheck.iol_in_matrix.bypass_words"), "crosscheck block present")
    eq(config.get_param(params, "matrix_params.sorter_areas"), [1], "sorter_areas lives under matrix_params")
    ok(os.path.isabs(params["iolist_path"]), "the shipped iolist_path is absolute")


if __name__ == "__main__":
    import sys
    sys.exit(run("params", [
        ("load_resolves_document_paths", test_load_resolves_document_paths),
        ("get_param_reads_nested_values", test_get_param_reads_nested_values),
        ("get_param_missing_returns_default", test_get_param_missing_returns_default),
        ("shipped_project_params_loads", test_shipped_project_params_loads),
    ]))
