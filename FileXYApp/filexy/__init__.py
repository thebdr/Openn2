"""filexy - a fast, embeddable Tk table viewer (extracted from Pipeline4App's DataGrid).

Virtual-rendered canvas grid: gridlines, zebra, per-cell fonts, data-adapted resizable columns,
tri-state NATURAL sort, cascade filters (substring / regex / Excel-style pick list) with removable
chips, global quick search (Ctrl+F), TSV copy (Ctrl+C), row-detail cards, column stats.

Split: `core` (pure, Tk-free - also the executable spec for the planned Rust engine port),
`grid` (the Tk widget), `theme` (rebindable palette/fonts for embedders), `files` (csv/xlsx
loaders), `app` (the standalone window - `python launch_viewer.py [file]`)."""

__version__ = "0.1"

from filexy.grid import DataGrid          # noqa: F401  (the package's main export)
