"""The table viewer's PURE core - no tkinter, no I/O. Everything here is deterministic and
unit-testable (pixel-measure functions are injected), and doubles as the executable SPEC for the
planned Rust port of this engine.

Concepts:
- rows are lists of DISPLAY strings (one line per cell - `sanitize`); the source order never changes.
- a VIEW is a list of source row indices: `apply_filters` narrows it, `sorted_view` permutes it.
- filters are dict specs {col, text, regex} | {col, values}; col None = the GLOBAL quick search
  (any cell may match). Filters AND together - the cascade: each was added over the then-visible
  rows, and the conjunction reproduces exactly that narrowing.
- sorting is NATURAL (digit runs compare numerically: I2.2 < I2.10 < I10.1) and tri-state
  (`cycle_sort`: asc -> desc -> released/original order).
"""
from __future__ import annotations

import re

LONG_CELL_CHARS = 64        # a cell longer than this renders in the small NARROW font
MIN_COL_W, MAX_COL_W = 60, 420
MIN_DRAG_W, FIT_MAX_W = 30, 1200   # bounds for MANUAL resizing / the double-click auto-fit
RESIZE_TOL = 5              # px around a header separator that grabs it for resize
PAD_X = 6                   # horizontal cell padding (each side)
_SAMPLE_ROWS = 200          # rows sampled for the column-width pass
_ELLIPSIS = "…"


# --- layout (measure functions injected) ------------------------------------------------------------ #
def cell_kind(text: str) -> str:
    """'small' when the cell exceeds LONG_CELL_CHARS (the smaller narrow font), else 'normal'."""
    return "small" if len(text) > LONG_CELL_CHARS else "normal"


def compute_col_widths(columns, rows, measure_normal, measure_small, measure_header) -> list:
    """Per-column pixel widths adapted to the data: the widest of the header and the sampled cells
    (each measured in ITS OWN rendering font, long cells capped at LONG_CELL_CHARS chars for the
    measure), clamped to [MIN_COL_W, MAX_COL_W]."""
    widths = []
    for c, column in enumerate(columns):
        width = measure_header(str(column)) + 2 * PAD_X
        for row in rows[:_SAMPLE_ROWS]:
            cell = str(row[c]) if c < len(row) else ""
            if cell_kind(cell) == "small":
                width = max(width, measure_small(cell[:LONG_CELL_CHARS]) + 2 * PAD_X)
            else:
                width = max(width, measure_normal(cell) + 2 * PAD_X)
        widths.append(max(MIN_COL_W, min(MAX_COL_W, width)))
    return widths


def fit_text(text: str, avail_px: int, measure) -> str:
    """`text` truncated with an ellipsis to fit `avail_px` (binary search over the cut point)."""
    if measure(text) <= avail_px:
        return text
    lo, hi = 0, len(text)
    while lo < hi:                                  # the longest prefix whose prefix+ellipsis fits
        mid = (lo + hi + 1) // 2
        if measure(text[:mid] + _ELLIPSIS) <= avail_px:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo] + _ELLIPSIS


def sanitize(cell) -> str:
    """One display line per cell: the first line of a multi-line value + an ellipsis marker."""
    text = "" if cell is None else str(cell)
    if "\n" in text:
        return text.split("\n", 1)[0] + _ELLIPSIS
    return text


def cell_at(widths, row_h, n_rows, x, y):
    """The `(row, col, cell_x0)` under canvas point (x, y), or None outside the data - the in-cell
    editor's hit test."""
    if y < 0 or row_h <= 0:
        return None
    row = int(y // row_h)
    if row >= n_rows:
        return None
    x0 = 0
    for col, width in enumerate(widths):
        if x0 <= x < x0 + width:
            return row, col, x0
        x0 += width
    return None


def boundary_at(widths, x, tol: int = RESIZE_TOL):
    """The column index whose RIGHT edge (the header separator) sits within `tol` px of canvas-x `x` -
    the resize grab zone - else None."""
    edge = 0
    for i, width in enumerate(widths):
        edge += width
        if abs(x - edge) <= tol:
            return i
    return None


def fit_col_width(columns, rows, c, measure_normal, measure_small, measure_header) -> int:
    """The double-click auto-fit width for column `c`: the widest of the header and EVERY row's cell
    (each measured in its rendering font), clamped [MIN_DRAG_W, FIT_MAX_W]. Unlike the initial layout
    there is NO MAX_COL_W cap and NO row sampling - a fit means the content actually fits."""
    width = measure_header(str(columns[c])) + 2 * PAD_X
    for row in rows:
        cell = row[c] if c < len(row) else ""
        measure = measure_small if cell_kind(cell) == "small" else measure_normal
        width = max(width, measure(cell) + 2 * PAD_X)
    return max(MIN_DRAG_W, min(FIT_MAX_W, width))


# --- sorting ---------------------------------------------------------------------------------------- #
_NAT_NUM = re.compile(r"(\d+)")


def natural_key(text) -> tuple:
    """Numeric-aware sort key: 'I10.1' sorts after 'I2.0' and '10' after '9' (a digit run compares as
    its number, the rest case-insensitively). Blank cells sort LAST."""
    text = str(text)
    if not text:
        return ((2, ""),)
    return tuple((0, int(part)) if part.isdigit() else (1, part.casefold())
                 for part in _NAT_NUM.split(text) if part != "")


def cycle_sort(state, col: int):
    """The header-click tri-state: unsorted -> (col,'asc') -> (col,'desc') -> released (None).
    A click on a DIFFERENT column starts fresh at 'asc'."""
    if state is None or state[0] != col:
        return (col, "asc")
    return (col, "desc") if state[1] == "asc" else None


def sorted_view(rows, view, sort) -> list:
    """`view` (source indices) ordered by the sort state - NON-destructive: the source rows never
    move, only the view permutes; sort=None returns the original document order. Stable + natural."""
    if sort is None:
        return list(view)
    col, direction = sort
    return sorted(view, key=lambda i: natural_key(rows[i][col] if col < len(rows[i]) else ""),
                  reverse=(direction == "desc"))


# --- filters (cascade) + quick search ---------------------------------------------------------------- #
def filter_passes(cell: str, spec: dict) -> bool:
    """One filter spec against one display cell. A `values` set filters by membership (the Excel-style
    pick list); else `text` matches as a regex (`regex: True`; a broken pattern matches nothing) or a
    case-insensitive substring. An empty spec passes everything."""
    if spec.get("values") is not None:
        return cell in spec["values"]
    pattern = spec.get("text", "")
    if not pattern:
        return True
    if spec.get("regex"):
        try:
            return re.search(pattern, cell, re.IGNORECASE) is not None
        except re.error:
            return False
    return pattern.casefold() in cell.casefold()


def apply_filters(rows, filters) -> list:
    """The visible SOURCE row indices: the rows passing EVERY filter. A spec with col None is the
    GLOBAL quick search - the row passes when ANY of its cells matches. Filters compose as AND -
    each one was added over the then-visible rows (cascade), and the conjunction reproduces exactly
    that narrowing regardless of evaluation order."""
    view = []
    for i, row in enumerate(rows):
        for spec in filters:
            c = spec.get("col")
            if c is None:                             # the quick search: any cell may match
                if not any(filter_passes(cell, spec) for cell in row):
                    break
            elif not filter_passes(row[c] if c < len(row) else "", spec):
                break
        else:
            view.append(i)
    return view


def distinct_values(rows, view, col: int, cap: int = 1000) -> list:
    """The column's distinct values among the VISIBLE rows, natural-sorted, capped - the cascade rule:
    the filter popup offers only what the previous filters left on screen (Excel behaviour)."""
    seen = {(rows[i][col] if col < len(rows[i]) else "") for i in view}
    return sorted(seen, key=natural_key)[:cap]


# --- selection --------------------------------------------------------------------------------------- #
def updated_selection(selected, anchor, row: int, ctrl: bool = False, shift: bool = False) -> tuple:
    """The next `(selected_set, anchor)` after a click on `row` (the standard list-selection model):
    a plain click selects just that row; Ctrl toggles it; Shift extends from the anchor (inclusive).
    The anchor moves on plain/Ctrl clicks and stays put across Shift extensions."""
    selected = set(selected)
    if shift and anchor is not None:
        lo, hi = sorted((anchor, row))
        return set(range(lo, hi + 1)), anchor
    if ctrl:
        selected ^= {row}
        return selected, row
    return {row}, row


# --- export + stats ---------------------------------------------------------------------------------- #
def to_tsv(columns, rows, view, header: bool = True) -> str:
    """The view as clipboard-ready TSV (Excel pastes it into cells). Cells are display strings
    already; embedded tabs collapse to spaces so the column structure survives."""
    def line(cells):
        return "\t".join(str(c).replace("\t", " ") for c in cells)
    out = [line(columns)] if header else []
    out += [line(rows[i]) for i in view]
    return "\n".join(out)


def column_stats(rows, view, col: int) -> dict:
    """One column's stats over the VISIBLE rows: {rows, blank, distinct, numeric, sum, min, max}
    (sum/min/max only when at least one cell parses as a number) - the filter popup's footer."""
    values = [(rows[i][col] if col < len(rows[i]) else "") for i in view]
    nonblank = [v for v in values if v != ""]
    numbers = []
    for v in nonblank:
        try:
            numbers.append(float(v))
        except ValueError:
            pass
    out = {"rows": len(values), "blank": len(values) - len(nonblank),
           "distinct": len(set(nonblank)), "numeric": len(numbers)}
    if numbers:
        out.update(sum=sum(numbers), min=min(numbers), max=max(numbers))
    return out


def stats_text(stats: dict) -> str:
    """`column_stats` rendered as the popup's one-line footer."""
    text = f"{stats['rows']} rows · {stats['distinct']} distinct"
    if stats["blank"]:
        text += f" · {stats['blank']} blank"
    if stats.get("numeric"):
        text += (f" · Σ {stats['sum']:g} · min {stats['min']:g} · max {stats['max']:g}")
    return text
