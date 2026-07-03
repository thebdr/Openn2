"""Standalone sanity for tableviewer.core - runnable with a bare `python tests/test_core.py` (no
harness, no tkinter). The FULL behaviour suite lives in Pipeline4App's gate and exercises this same
package through the pipeline4.gui.datagrid shim; this file keeps the extracted package honest when
it ships alone."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tableviewer import core  # noqa: E402

failures = []


def check(cond, label):
    if not cond:
        failures.append(label)
    print(("  PASS  " if cond else "  FAIL  ") + label)


check(sorted(["I10.1", "I2.0", "I2.10", "I2.2"], key=core.natural_key)
      == ["I2.0", "I2.2", "I2.10", "I10.1"], "natural sort")
check(core.cycle_sort(core.cycle_sort(core.cycle_sort(None, 1), 1), 1) is None, "tri-state sort cycle")

rows = [["S1", "I2.0", "door"], ["S1", "I10.1", "estop"], ["S2", "I2.2", "door"]]
check(core.apply_filters(rows, [{"col": 0, "text": "S1"}]) == [0, 1], "column filter")
check(core.apply_filters(rows, [{"col": 0, "text": "S1"}, {"col": 2, "values": {"door"}}]) == [0],
      "cascade AND")
check(core.apply_filters(rows, [{"col": None, "text": "estop"}]) == [1], "quick search (any cell)")
check(core.sorted_view(rows, [0, 1, 2], (1, "asc")) == [0, 2, 1], "natural view sort")
check(core.distinct_values(rows, [0, 1], 2) == ["door", "estop"], "distinct of the visible rows")

tsv = core.to_tsv(["A", "B"], [["1", "x\ty"], ["2", "z"]], [1, 0])
check(tsv == "A\tB\n2\tz\n1\tx y", "TSV export (view order, tabs collapsed)")

stats = core.column_stats([["1.5"], ["2.5"], [""], ["x"]], [0, 1, 2, 3], 0)
check(stats == {"rows": 4, "blank": 1, "distinct": 3, "numeric": 2, "sum": 4.0, "min": 1.5, "max": 2.5},
      "column stats")
check("Σ 4" in core.stats_text(stats) and "1 blank" in core.stats_text(stats), "stats footer text")

sel, anchor = core.updated_selection({1}, 1, 4, shift=True)
check(sel == {1, 2, 3, 4} and anchor == 1, "shift-range selection")

check(core.fit_text("abcdef", 30, lambda t: 10 * len(t)) == "ab…", "ellipsis fit")
check(core.cell_kind("x" * 65) == "small" and core.cell_kind("x" * 64) == "normal", "long-cell font rule")

print(f"-> {'FAILED: ' + '; '.join(failures) if failures else 'all passed'}")
sys.exit(1 if failures else 0)
