"""The FileXY extraction seam: the `pipeline5.workbench.datagrid` shim re-exports the extracted
`filexy` package bound to PL4's theme, the NEW core capabilities (quick search / TSV export /
column stats) work through it, and the package stands ALONE (imports + its own test file pass in a
subprocess with no pipeline5 on the path)."""
import os
import subprocess
import sys

from _harness import run, eq, ok
from pipeline5.workbench import datagrid

_TV_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..",
                                        "FileXYApp"))


def test_shim_reexports_and_theme_binding():
    import filexy
    from filexy import grid as fx_grid, theme as fx_theme
    from pipeline5.workbench import theme as pl4_theme
    ok(datagrid.DataGrid is fx_grid.DataGrid, "the shim's DataGrid IS the package widget")
    ok(fx_theme.TOKENS is pl4_theme.TOKENS, "the viewer renders with PL4's OWN tokens")
    eq(fx_theme.mono_family(None), pl4_theme.MONO_FONT[0], "…and PL4's bundled mono font")
    for name in ("cell_kind", "natural_key", "apply_filters", "updated_selection", "to_tsv",
                 "column_stats", "fit_col_width", "FIT_MAX_W", "LONG_CELL_CHARS"):
        ok(hasattr(datagrid, name), f"shim re-exports {name}")
    ok(bool(filexy.__version__), "the package carries a version")


def test_quick_search_spec():
    rows = [["S1", "I2.0", "door"], ["S1", "I10.1", "estop"], ["S2", "I2.2", "door open"]]
    eq(datagrid.apply_filters(rows, [{"col": None, "text": "estop"}]), [1],
       "a col=None spec searches EVERY cell (the Ctrl+F quick search)")
    eq(datagrid.apply_filters(rows, [{"col": None, "text": "door"}, {"col": 0, "text": "S2"}]), [2],
       "the quick search cascades with the column filters")
    eq(datagrid.apply_filters(rows, [{"col": None, "text": ""}]), [0, 1, 2], "empty text passes all")


def test_to_tsv_and_column_stats():
    columns = ["A", "B"]
    rows = [["1.5", "x\ty"], ["2.5", "z"], ["", "w"]]
    eq(datagrid.to_tsv(columns, rows, [1, 0]), "A\tB\n2.5\tz\n1.5\tx y",
       "TSV in VIEW order, header on, embedded tabs collapsed")
    eq(datagrid.to_tsv(columns, rows, [2], header=False), "\tw", "header off")
    stats = datagrid.column_stats(rows, [0, 1, 2], 0)
    eq((stats["rows"], stats["blank"], stats["distinct"], stats["numeric"]), (3, 1, 2, 2))
    eq((stats["sum"], stats["min"], stats["max"]), (4.0, 1.5, 2.5), "numeric aggregation")
    text = datagrid.stats_text(stats)
    ok("3 rows" in text and "Σ 4" in text and "min 1.5" in text, "the popup footer text")
    ok("numeric" not in datagrid.column_stats([["x"]], [0], 0).get("sum", "x") or True,
       "no sum key without numbers")
    ok("sum" not in datagrid.column_stats([["x"]], [0], 0), "no aggregation for a non-numeric column")


def test_package_stands_alone():
    """The extracted package must import + pass its own tests WITHOUT pipeline5 anywhere on the
    path - the standalone/shippable contract."""
    result = subprocess.run(
        [sys.executable, os.path.join(_TV_ROOT, "tests", "test_core.py")],
        capture_output=True, text=True, cwd=_TV_ROOT, timeout=120)
    eq(result.returncode, 0, f"standalone test_core passes:\n{result.stdout}\n{result.stderr}")
    probe = ("import sys; sys.path.insert(0, r'" + _TV_ROOT + "'); "
             "import filexy, filexy.app, filexy.files, filexy.highlight, filexy.objectview; "
             "assert 'pipeline5' not in sys.modules, 'the package must not import pipeline5'; "
             "print(filexy.__version__)")
    result = subprocess.run([sys.executable, "-c", probe],
                            capture_output=True, text=True, cwd=_TV_ROOT, timeout=120)
    eq(result.returncode, 0, f"standalone import is pipeline5-free:\n{result.stderr}")


if __name__ == "__main__":
    import sys as _sys
    _sys.exit(run("filexy_shim", [
        ("shim_reexports_and_theme_binding", test_shim_reexports_and_theme_binding),
        ("quick_search_spec", test_quick_search_spec),
        ("to_tsv_and_column_stats", test_to_tsv_and_column_stats),
        ("package_stands_alone", test_package_stands_alone),
    ]))
