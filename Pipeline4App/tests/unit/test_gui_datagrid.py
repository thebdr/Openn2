"""The shared data grid's pure half (gui/datagrid.py): the long-cell font rule, the data-adapted
column widths (measure functions injected), the ellipsis fit, and the one-line cell sanitizer.
The canvas rendering (gridlines/zebra/virtual slice) is a scripted + manual check."""
from _harness import run, eq, ok
from pipeline4.gui import datagrid


def _measure(px_per_char):
    return lambda text: px_per_char * len(text)


def test_cell_kind_boundary():
    eq(datagrid.cell_kind("x" * 64), "normal", "64 chars stays the normal font")
    eq(datagrid.cell_kind("x" * 65), "small", "65 chars -> the small narrow font")
    eq(datagrid.cell_kind(""), "normal", "empty is normal")


def test_compute_col_widths_adapts_to_data():
    normal, small, header = _measure(10), _measure(4), _measure(10)
    columns = ["id", "description"]
    rows = [["1", "short"],
            ["2", "a much longer description cell than the header is"],   # 50 chars, normal font
            ["3"]]                                                          # ragged - no crash
    widths = datagrid.compute_col_widths(columns, rows, normal, small, header)
    eq(widths[0], datagrid.MIN_COL_W, "a narrow column clamps to the minimum")
    eq(widths[1], min(datagrid.MAX_COL_W, 10 * 50 + 12), "the widest DATA cell sizes the column")
    ok(widths[1] == datagrid.MAX_COL_W, "and the 500px measure clamps to MAX_COL_W")


def test_compute_col_widths_long_cells_measure_small():
    normal, small, header = _measure(10), _measure(4), _measure(10)
    long_cell = "y" * 100                       # > LONG_CELL_CHARS -> measured in the SMALL font,
    widths = datagrid.compute_col_widths(["c"], [[long_cell]], normal, small, header)
    eq(widths[0], 4 * datagrid.LONG_CELL_CHARS + 12,
       "a long cell measures its first 64 chars in the small font (4px/char), not the normal 10")


def test_fit_text_ellipsis():
    measure = _measure(10)
    eq(datagrid.fit_text("abcdef", 60, measure), "abcdef", "fits -> unchanged")
    fitted = datagrid.fit_text("abcdefghij", 60, measure)
    ok(fitted.endswith("…") and len(fitted) <= 6, f"truncates with an ellipsis: {fitted!r}")
    ok(measure(fitted) <= 60, "the fitted text actually fits")
    eq(datagrid.fit_text("abc", 5, measure), "…", "hopelessly narrow -> just the ellipsis")


def test_sanitize_one_line():
    eq(datagrid.sanitize("plain"), "plain")
    eq(datagrid.sanitize("first\nsecond"), "first…", "multi-line shows the first line + a marker")
    eq(datagrid.sanitize(None), "", "None -> empty")
    eq(datagrid.sanitize(42), "42", "non-strings stringify")


if __name__ == "__main__":
    import sys
    sys.exit(run("gui_datagrid", [
        ("cell_kind_boundary", test_cell_kind_boundary),
        ("compute_col_widths_adapts_to_data", test_compute_col_widths_adapts_to_data),
        ("compute_col_widths_long_cells_measure_small", test_compute_col_widths_long_cells_measure_small),
        ("fit_text_ellipsis", test_fit_text_ellipsis),
        ("sanitize_one_line", test_sanitize_one_line),
    ]))
