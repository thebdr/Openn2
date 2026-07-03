# Table Viewer

A fast, embeddable Tk table viewer — extracted from Pipeline4App's shared data grid so it can ship
standalone and be reused by future projects.

## Standalone

```
python launch_viewer.py [path\to\table.csv|.xlsx]
```

Open a CSV (delimiter-sniffed) or an Excel workbook (sheet picker). Requires Python 3.10+ with
tkinter; `openpyxl` only for xlsx files.

**In the grid**
- **Sort** — click a column header: ascending → descending → released (natural order: `I2.2 <
  I2.10 < I10.1`, blanks last). Non-destructive — only the view permutes.
- **Filter** — right-click a header: substring, regex, or an Excel-style pick list of the VISIBLE
  rows' distinct values (cascade: each filter narrows what the previous left), with the column's
  stats as the footer. Active sort/filters are removable CHIPS above the header.
- **Quick search** — Ctrl+F (or the toolbar box): live, matches any cell.
- **Copy / export** — Ctrl+C copies the selection (or the whole filtered view) as TSV; the toolbar
  exports the current view to CSV.
- **Row detail** — double-click a row: the full row as a vertical name/value card.
- **Select** — click / Ctrl / Shift / drag; **resize** — drag a header separator, double-click it
  to auto-fit.

## Embedding

```python
from tableviewer.grid import DataGrid
grid = DataGrid(parent, mode="dark", selectable=True, on_context=my_menu)
grid.set_data(columns, rows, row_fg=my_row_colors)
```

Rebind the look before constructing widgets (`tableviewer.theme`): assign your own `TOKENS`
(same role names) and/or `mono_family` / `narrow_family` resolvers. Pipeline4App embeds exactly
this way through its `pipeline4/gui/datagrid.py` shim.

## Layout

- `tableviewer/core.py` — the PURE engine (layout, natural sort, cascade filters, quick search,
  selection model, TSV export, column stats). No tkinter, no I/O; fully unit-testable, and the
  executable spec for the planned Rust port (calamine + PyO3).
- `tableviewer/grid.py` — the Tk widget + popups (filter / quick search / row detail).
- `tableviewer/theme.py` — rebindable palette + fonts; minimal standalone styling.
- `tableviewer/files.py` — CSV/xlsx loaders.
- `tableviewer/app.py` + `launch_viewer.py` — the standalone window.
- `tests/test_core.py` — standalone sanity tests (`python tests/test_core.py`); the full behaviour
  suite lives in Pipeline4App's gate and runs against this package through the shim.

Deferred: frozen/pinned columns (needs a two-region canvas rework); the Rust core port.
