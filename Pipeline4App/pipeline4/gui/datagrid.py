"""The shared data grid - now the EMBEDDING SHIM over the extracted `tableviewer` package
(../../TableViewerApp; the user-agreed extraction: the viewer ships standalone and embeddable,
PL4 is its first embedder). This module keeps the historical `pipeline4.gui.datagrid` surface -
the widget, the pure helpers, the constants - so the hosts (files_panel, db_explorer,
findings_panel) and the test suite are untouched.

The shim does three things:
1. puts the sibling TableViewerApp on sys.path (PL4 ships as source; the two live side by side);
2. binds `tableviewer.theme` to PL4's OWN tokens + fonts BEFORE any widget is built, so the grid
   is pixel-identical to the pre-extraction look and follows PL4's theme toggle;
3. re-exports the package's public names.

New capability arriving with the extraction (in every PL4 table at once): Ctrl+F global quick
search (a removable chip), Ctrl+C TSV copy of the selection/filtered view, a double-click ROW
DETAIL card on read-only grids, and column stats in the filter popup. The viewer itself is
documented in TableViewerApp/README.md."""
from __future__ import annotations

import os
import sys

_TV_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..",
                                        "TableViewerApp"))
if os.path.isdir(_TV_ROOT) and _TV_ROOT not in sys.path:
    sys.path.insert(0, _TV_ROOT)

from pipeline4.gui import theme as _pl4_theme            # noqa: E402
from tableviewer import theme as _tv_theme               # noqa: E402

# PL4 is the embedder: the viewer renders with PL4's palette + bundled fonts (bound before any
# DataGrid exists - tableviewer.theme is read at call time, so this is all the wiring needed).
_tv_theme.TOKENS = _pl4_theme.TOKENS
_tv_theme.mono_family = lambda _widget: _pl4_theme.MONO_FONT[0]
_tv_theme.narrow_family = _pl4_theme.narrow_family

from tableviewer.core import (                           # noqa: E402,F401
    LONG_CELL_CHARS, MIN_COL_W, MAX_COL_W, MIN_DRAG_W, FIT_MAX_W, RESIZE_TOL,
    apply_filters, boundary_at, cell_at, cell_kind, column_stats, compute_col_widths,
    cycle_sort, distinct_values, filter_passes, fit_col_width, fit_text, frozen_width,
    hit_x, natural_key, sanitize, sorted_view, stats_text, to_tsv, updated_selection,
)
from tableviewer.grid import DataGrid, _FilterPopup      # noqa: E402,F401
