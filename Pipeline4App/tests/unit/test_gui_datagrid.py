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


def test_render_kind_reexpands_on_width():
    normal = _measure(10)
    long_cell = "x" * 80                        # cell_kind 'small' (over the 64-char rule)
    eq(datagrid.render_kind(long_cell, 300, normal), "small", "doesn't fit normal -> narrow font")
    eq(datagrid.render_kind(long_cell, 900, normal), "normal",
       "a column widened past the text RE-EXPANDS it (the static rule never recovered)")
    eq(datagrid.render_kind("y" * 30, 100, normal), "normal",
       "a short overflowing cell never narrows - it ellipsizes in the normal font")


def test_pad_columns_ragged_file():
    # the InstanceDBs.csv shape: a 2-cell '#' comment first row over 5-cell '@' data rows
    cols = datagrid.pad_columns(["#", "Instance DBs created..."],
                                [["%", "Name", "InstanceOf", "Number", "Folder"],
                                 ["@", "EMPB_1", "00_PB", "", "00_PB"]])
    eq(cols, ["#", "Instance DBs created...", "", "", ""],
       "the header pads to the WIDEST row - no data column hides behind a short first row")
    eq(datagrid.pad_columns(["a", "b"], [["1"]]), ["a", "b"], "an already-wide header stays put")
    eq(datagrid.pad_columns([], []), [], "empty table")
    eq(datagrid.pad_columns([1, 2], [[""] * 3]), ["1", "2", ""], "non-string headers stringify")


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


def test_cell_at_hit_test():
    widths, row_h, n = [100, 200], 20, 3
    eq(datagrid.cell_at(widths, row_h, n, 50, 10), (0, 0, 0), "first cell")
    eq(datagrid.cell_at(widths, row_h, n, 150, 45), (2, 1, 100), "row 2, col 1, cell x0=100")
    eq(datagrid.cell_at(widths, row_h, n, 150, 70), None, "below the data")
    eq(datagrid.cell_at(widths, row_h, n, 350, 10), None, "right of the table")
    eq(datagrid.cell_at(widths, row_h, n, 50, -5), None, "above the table")


def test_boundary_at_grab_zones():
    widths = [100, 200, 60]                     # separators at x = 100, 300, 360
    eq(datagrid.boundary_at(widths, 100), 0, "dead-on the first separator")
    eq(datagrid.boundary_at(widths, 104), 0, "within the +tolerance")
    eq(datagrid.boundary_at(widths, 96), 0, "within the -tolerance")
    eq(datagrid.boundary_at(widths, 300), 1, "the second separator")
    eq(datagrid.boundary_at(widths, 360), 2, "the RIGHTMOST separator is grabbable too")
    eq(datagrid.boundary_at(widths, 200), None, "mid-column is not a separator")
    eq(datagrid.boundary_at(widths, 380), None, "past the table is nothing")
    eq(datagrid.boundary_at([], 10), None, "no columns, no separators")


def test_fit_col_width_uncapped_and_fonts():
    normal, small, header = _measure(10), _measure(4), _measure(10)
    columns = ["c"]
    rows = [["x" * 60]]                          # 60 chars, normal font -> 600px + padding
    w = datagrid.fit_col_width(columns, rows, 0, normal, small, header)
    eq(w, 600 + 12, "the auto-fit ignores MAX_COL_W (fit means fit)")
    long_rows = [["y" * 100]]                    # long cell -> the SMALL font measures it
    eq(datagrid.fit_col_width(columns, long_rows, 0, normal, small, header), 4 * 100 + 12,
       "a long cell fits at its small-font width (every char, no 64-char cap here)")
    eq(datagrid.fit_col_width(["wide header"], [["x"]], 0, normal, small, header), 10 * 11 + 12,
       "the header participates in the fit")
    eq(datagrid.fit_col_width(columns, [["z" * 500]], 0, normal, small, header),
       datagrid.FIT_MAX_W, "the fit clamps at FIT_MAX_W")
    eq(datagrid.fit_col_width(columns, [[""]], 0, normal, small, header),
       max(datagrid.MIN_DRAG_W, 10 + 12), "an empty column falls to the header/minimum")


def test_pinned_column_hit_mapping():
    """The pinned-strip hit test: inside the strip the widget x IS the natural x (the first
    columns' natural positions are [0, frozen_w)); past it, normal canvas scrolling applies;
    with no strip it degenerates to plain canvasx."""
    eq(datagrid.frozen_width([100, 80, 200], 2), 180, "the strip width = the first n columns")
    eq(datagrid.frozen_width([100, 80], 0), 0, "unpinned -> no strip")
    eq(datagrid.hit_x(50, 300.0, 180), 50, "a click INSIDE the strip maps to the pinned column")
    eq(datagrid.hit_x(200, 300.0, 180), 500.0, "past the strip -> x_left + widget_x (scrolled)")
    eq(datagrid.hit_x(200, 0.0, 180), 200.0, "unscrolled: identical to canvasx either way")
    eq(datagrid.hit_x(50, 300.0, 0), 350.0, "no strip -> plain canvasx")
    # unambiguous: past-strip hits always land BEYOND the covered zone (>= x_left + frozen_w)
    ok(datagrid.hit_x(180, 300.0, 180) >= 300.0 + 180, "the covered zone is unreachable")


def test_updated_selection_model():
    """The multi-select click model: plain replaces, Ctrl toggles, Shift ranges from the anchor."""
    sel, anchor = datagrid.updated_selection(set(), None, 3)
    eq((sel, anchor), ({3}, 3), "a plain click selects just that row + moves the anchor")
    sel, anchor = datagrid.updated_selection(sel, anchor, 5, ctrl=True)
    eq((sel, anchor), ({3, 5}, 5), "Ctrl adds + moves the anchor")
    sel, anchor = datagrid.updated_selection(sel, anchor, 5, ctrl=True)
    eq((sel, anchor), ({3}, 5), "Ctrl on a selected row toggles it OFF")
    sel, anchor = datagrid.updated_selection(sel, anchor, 1, shift=True)
    eq((sel, anchor), ({1, 2, 3, 4, 5}, 5), "Shift selects the anchor..row range (anchor stays)")
    sel, anchor = datagrid.updated_selection(sel, anchor, 7, shift=True)
    eq((sel, anchor), ({5, 6, 7}, 5), "a second Shift re-ranges from the SAME anchor")
    sel, anchor = datagrid.updated_selection(sel, None, 2, shift=True)
    eq((sel, anchor), ({2}, 2), "Shift with no anchor degrades to a plain click")
    sel, anchor = datagrid.updated_selection({1, 2, 9}, 9, 4)
    eq((sel, anchor), ({4}, 4), "a plain click REPLACES a multi-selection")


def test_natural_sort_key():
    rows = ["I10.1", "I2.0", "I2.10", "I2.2"]
    eq(sorted(rows, key=datagrid.natural_key), ["I2.0", "I2.2", "I2.10", "I10.1"],
       "digit runs compare numerically (I2.2 < I2.10 < I10.1)")
    eq(sorted(["10", "9", "100"], key=datagrid.natural_key), ["9", "10", "100"], "'10' after '9'")
    eq(sorted(["b", "", "a"], key=datagrid.natural_key), ["a", "b", ""], "blank cells sort LAST")
    eq(sorted(["Beta", "alpha"], key=datagrid.natural_key), ["alpha", "Beta"], "case-insensitive")


def test_cycle_sort_tristate():
    s1 = datagrid.cycle_sort(None, 2)
    eq(s1, (2, "asc"), "first click -> ascending")
    s2 = datagrid.cycle_sort(s1, 2)
    eq(s2, (2, "desc"), "second click -> descending")
    eq(datagrid.cycle_sort(s2, 2), None, "third click RELEASES the sort (original order)")
    eq(datagrid.cycle_sort(s2, 0), (0, "asc"), "a different column starts fresh at asc")


def test_filter_passes_modes():
    ok(datagrid.filter_passes("NET SAFETY 50", {"col": 0, "text": "safety"}), "substring, case-insensitive")
    ok(not datagrid.filter_passes("NET SAFETY 50", {"col": 0, "text": "sorter"}))
    ok(datagrid.filter_passes("I110.0", {"col": 0, "text": r"^I\d+\.0$", "regex": True}), "regex mode")
    ok(not datagrid.filter_passes("Q1.0", {"col": 0, "text": r"^I", "regex": True}))
    ok(not datagrid.filter_passes("x", {"col": 0, "text": "([", "regex": True}), "a broken regex matches nothing")
    ok(datagrid.filter_passes("A", {"col": 0, "values": {"A", "B"}}), "value-set membership")
    ok(not datagrid.filter_passes("C", {"col": 0, "values": {"A", "B"}}))
    ok(datagrid.filter_passes("anything", {"col": 0, "text": ""}), "an empty spec passes everything")


def test_apply_filters_cascade_and_sorted_view():
    rows = [["S1", "I2.0"], ["S1", "I10.1"], ["S2", "I2.2"], ["S1", "Q1.0"]]
    view = datagrid.apply_filters(rows, [{"col": 0, "text": "S1"}])
    eq(view, [0, 1, 3], "one filter narrows to the matching source indices")
    view = datagrid.apply_filters(rows, [{"col": 0, "text": "S1"}, {"col": 1, "text": "^I", "regex": True}])
    eq(view, [0, 1], "the second filter narrows the FIRST filter's survivors (cascade = AND)")
    eq(datagrid.sorted_view(rows, view, (1, "asc")), [0, 1], "natural asc: I2.0 before I10.1")
    eq(datagrid.sorted_view(rows, view, (1, "desc")), [1, 0], "desc reverses")
    eq(datagrid.sorted_view(rows, view, None), [0, 1], "released sort -> the original document order")
    eq(datagrid.distinct_values(rows, view, 1), ["I2.0", "I10.1"],
       "the filter popup offers only the VISIBLE rows' values, natural-sorted")
    eq(datagrid.distinct_values(rows, [0, 1, 2, 3], 0), ["S1", "S2"], "distinct + full view")


if __name__ == "__main__":
    import sys
    sys.exit(run("gui_datagrid", [
        ("cell_kind_boundary", test_cell_kind_boundary),
        ("render_kind_reexpands_on_width", test_render_kind_reexpands_on_width),
        ("pad_columns_ragged_file", test_pad_columns_ragged_file),
        ("compute_col_widths_adapts_to_data", test_compute_col_widths_adapts_to_data),
        ("compute_col_widths_long_cells_measure_small", test_compute_col_widths_long_cells_measure_small),
        ("fit_text_ellipsis", test_fit_text_ellipsis),
        ("sanitize_one_line", test_sanitize_one_line),
        ("cell_at_hit_test", test_cell_at_hit_test),
        ("boundary_at_grab_zones", test_boundary_at_grab_zones),
        ("fit_col_width_uncapped_and_fonts", test_fit_col_width_uncapped_and_fonts),
        ("pinned_column_hit_mapping", test_pinned_column_hit_mapping),
        ("updated_selection_model", test_updated_selection_model),
        ("natural_sort_key", test_natural_sort_key),
        ("cycle_sort_tristate", test_cycle_sort_tristate),
        ("filter_passes_modes", test_filter_passes_modes),
        ("apply_filters_cascade_and_sorted_view", test_apply_filters_cascade_and_sorted_view),
    ]))
