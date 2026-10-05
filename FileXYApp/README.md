# FileXY

A fast, embeddable Tk file viewer/editor — extracted from Pipeline4App so it can ship standalone
and be reused by future projects. Tables (the virtual data grid), text with syntax highlighting
(data-driven languages, Notepad++-UDL style), and structured-document object explorers
(yaml/json editable, xml read-only).

## Standalone

```
python launch_filexy.py [path\to\table.csv|.xlsx]
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
- **Pinned columns** — right-click a header → "Pin ≤ here": while x-scrolling, the first columns
  stay as a strip at the left edge (unpin from the same popup or the chip).
- **Select** — click / Ctrl / Shift / drag; **resize** — drag a header separator, double-click it
  to auto-fit.

## Embedding

```python
from filexy.grid import DataGrid
grid = DataGrid(parent, mode="dark", selectable=True, on_context=my_menu)
grid.set_data(columns, rows, row_fg=my_row_colors)
```

Rebind the look before constructing widgets (`filexy.theme`): assign your own `TOKENS`
(same role names) and/or `mono_family` / `narrow_family` resolvers. Pipeline5App embeds exactly
this way through its `pipeline5/workbench/datagrid.py` / `object_editor.py` shims (the frozen
Pipeline4App through `pipeline4/gui/datagrid.py`).

## Layout

- `filexy/core.py` — the PURE grid engine (layout, natural sort, cascade filters, quick search,
  selection model, TSV export, column stats). No tkinter, no I/O; fully unit-testable, and the
  executable spec for the planned Rust port (calamine + PyO3).
- `filexy/highlight.py` + `filexy/langs.json` — syntax highlighting: bespoke yaml/json/xml, plus
  DATA-DRIVEN languages à la Notepad++ UDL — a language is a JSON entry (extensions, comment
  markers, string quotes, keyword groups, extra regex rules), no code; `load_languages(path)`
  merges your own file over the shipped one (scl / sql / ini included). Hosts offer
  `available_kinds()` as a selectable language picker.
- `filexy/objectview.py` — the object explorer/editor (yaml/json scalar editing with `…` path
  pickers + Add-element; xml as a read-only structure tree); zebra, dividers, the highlight
  palette, Expand/Collapse all. An embedding host reads its `dirty` flag (an unsaved-changes guard)
  and re-themes it in place with `set_theme(mode)` - an unsaved edit survives a theme switch.
- `filexy/grid.py` — the Tk widget + popups (filter / quick search / row detail).
- `filexy/theme.py` — rebindable palette + fonts; minimal standalone styling.
- `filexy/files.py` — CSV/xlsx loaders.
- `filexy/app.py` + `launch_filexy.py` — the standalone window.
- `tests/test_core.py` — standalone sanity tests (`python tests/test_core.py`); the full behaviour
  suite lives in the embedding pipelines' gates and runs against this package through their shims
  (Pipeline5App: `test_gui_datagrid`, `test_gui_object_editor`, `test_filexy_shim` - the surface
  the Files tab relies on, `dirty` / `set_theme` - and `test_gui_files_discard`).

Deferred: the Rust core port (calamine + PyO3), an egui shell if the standalone exe needs it.
