"""The shared data grid - now the EMBEDDING SHIM over the extracted `filexy` package
(../../FileXYApp - renamed from TableViewerApp when the file-editor logic joined the viewer;
the user-agreed extraction: FileXY ships standalone and embeddable, PL4 is its first embedder).
This module keeps the historical `pipeline5.gui.datagrid` surface - the widget, the pure helpers,
the constants - so the hosts (files_panel, db_explorer, findings_panel) and the test suite are
untouched. The `_filexy` bootstrap (shared with the highlight/object_editor shims) puts the
sibling FileXYApp on sys.path and binds `filexy.theme` to PL4's tokens + fonts before any widget
is built.

New capability arriving with the extraction (in every PL4 table at once): Ctrl+F global quick
search (a removable chip), Ctrl+C TSV copy of the selection/filtered view, a double-click ROW
DETAIL card on read-only grids, and column stats in the filter popup. The viewer itself is
documented in FileXYApp/README.md."""
from __future__ import annotations

from pipeline5.gui import _filexy  # noqa: F401  (sys.path + theme binding - must run first)

from filexy.core import (                                # noqa: E402,F401
    LONG_CELL_CHARS, MIN_COL_W, MAX_COL_W, MIN_DRAG_W, FIT_MAX_W, RESIZE_TOL,
    apply_filters, boundary_at, cell_at, cell_kind, column_stats, compute_col_widths,
    cycle_sort, distinct_values, filter_passes, fit_col_width, fit_text, frozen_width,
    hit_x, natural_key, pad_columns, render_kind, sanitize, sorted_view, stats_text, to_tsv,
    updated_selection,
)
from filexy.grid import DataGrid, _FilterPopup           # noqa: E402,F401
