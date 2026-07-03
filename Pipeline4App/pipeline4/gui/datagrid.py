"""The shared data grid (the Files-tab CSV/xlsx viewers + the Database Explorer results) - read-only
by default, with optional IN-CELL editing (the Files-tab CSV viewer).

ttk.Treeview cannot draw cell gridlines on Tk 8.6 and its tags (fonts/colours) apply per ROW, never
per cell - so the user-requested look (grid borders, zebra rows, and a smaller NARROW font for cells
longer than LONG_CELL_CHARS) is drawn directly on a Canvas instead. VIRTUAL rendering: only the
visible row slice is drawn on each scroll tick, so a 2000-row result costs the same as a screenful.

Column widths ADAPT TO THE DATA: each column is sized to its widest sampled cell (measured in the
font that cell will actually use - a long cell measures in the small narrow font), clamped to
[MIN_COL_W, MAX_COL_W]; a cell wider than its column truncates with an ellipsis. Columns RESIZE BY
MOUSE: drag a header separator, or DOUBLE-CLICK it to auto-fit that column to its content (no cap
but FIT_MAX_W, no sampling).

SORT + CASCADE FILTERS (non-destructive): a header CLICK cycles the column's sort asc -> desc ->
released (natural order: digit runs compare numerically, so I10.1 > I2.0); a header RIGHT-CLICK
opens the column's filter popup (substring / regex / an Excel-style pick list of the VISIBLE rows'
distinct values - the cascade: each new filter narrows what the previous ones left). The source
rows never move - only the `_view` (source-index list) permutes/narrows; active sort/filters show
as removable CHIPS above the header with a `k of n rows` count. The width/fit/font/boundary/sort/
filter rules are pure helpers (measure functions injected) so they are unit-testable without a
display.
"""
from __future__ import annotations

import re
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

from pipeline4.gui import theme

LONG_CELL_CHARS = 64        # a cell longer than this renders in the small NARROW font
MIN_COL_W, MAX_COL_W = 60, 420
MIN_DRAG_W, FIT_MAX_W = 30, 1200   # bounds for MANUAL resizing / the double-click auto-fit
RESIZE_TOL = 5              # px around a header separator that grabs it for resize
_PAD_X = 6                  # horizontal cell padding (each side)
_SAMPLE_ROWS = 200          # rows sampled for the column-width pass
_ELLIPSIS = "…"


# --- pure helpers (measure functions injected - Tk-free testable) ---------------------------------- #
def cell_kind(text: str) -> str:
    """'small' when the cell exceeds LONG_CELL_CHARS (the smaller narrow font), else 'normal'."""
    return "small" if len(text) > LONG_CELL_CHARS else "normal"


def compute_col_widths(columns, rows, measure_normal, measure_small, measure_header) -> list:
    """Per-column pixel widths adapted to the data: the widest of the header and the sampled cells
    (each measured in ITS OWN rendering font, long cells capped at LONG_CELL_CHARS chars for the
    measure), clamped to [MIN_COL_W, MAX_COL_W]."""
    widths = []
    for c, column in enumerate(columns):
        width = measure_header(str(column)) + 2 * _PAD_X
        for row in rows[:_SAMPLE_ROWS]:
            cell = str(row[c]) if c < len(row) else ""
            if cell_kind(cell) == "small":
                width = max(width, measure_small(cell[:LONG_CELL_CHARS]) + 2 * _PAD_X)
            else:
                width = max(width, measure_normal(cell) + 2 * _PAD_X)
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
    """The visible SOURCE row indices: the rows passing EVERY filter. Filters compose as AND - each
    one was added over the then-visible rows (cascade), and the conjunction reproduces exactly that
    narrowing regardless of evaluation order."""
    view = []
    for i, row in enumerate(rows):
        for spec in filters:
            c = spec["col"]
            if not filter_passes(row[c] if c < len(row) else "", spec):
                break
        else:
            view.append(i)
    return view


def sorted_view(rows, view, sort) -> list:
    """`view` (source indices) ordered by the sort state - NON-destructive: the source rows never
    move, only the view permutes; sort=None returns the original document order. Stable + natural."""
    if sort is None:
        return list(view)
    col, direction = sort
    return sorted(view, key=lambda i: natural_key(rows[i][col] if col < len(rows[i]) else ""),
                  reverse=(direction == "desc"))


def distinct_values(rows, view, col: int, cap: int = 1000) -> list:
    """The column's distinct values among the VISIBLE rows, natural-sorted, capped - the cascade rule:
    the filter popup offers only what the previous filters left on screen (Excel behaviour)."""
    seen = {(rows[i][col] if col < len(rows[i]) else "") for i in view}
    return sorted(seen, key=natural_key)[:cap]


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


def fit_col_width(columns, rows, c, measure_normal, measure_small, measure_header) -> int:
    """The double-click auto-fit width for column `c`: the widest of the header and EVERY row's cell
    (each measured in its rendering font), clamped [MIN_DRAG_W, FIT_MAX_W]. Unlike the initial layout
    there is NO MAX_COL_W cap and NO row sampling - a fit means the content actually fits."""
    width = measure_header(str(columns[c])) + 2 * _PAD_X
    for row in rows:
        cell = row[c] if c < len(row) else ""
        measure = measure_small if cell_kind(cell) == "small" else measure_normal
        width = max(width, measure(cell) + 2 * _PAD_X)
    return max(MIN_DRAG_W, min(FIT_MAX_W, width))


# --- the widget -------------------------------------------------------------------------------------- #
class DataGrid(ttk.Frame):
    """Header canvas + body canvas (x-scroll synced), gridlines, zebra rows, per-cell fonts.
    With `editable=True` a DATA cell edits in place on double-click (single-line Entry overlay;
    Enter commits through `on_edit(row, col, new) -> bool`, Escape/focus-out cancels); `raw_of(row,
    col)` supplies the underlying value (the grid itself only holds the sanitized DISPLAY text).
    With `selectable=True` rows MULTI-select (click / Ctrl-toggle / Shift-range / click-DRAG a
    range); a right-click on an unselected row selects it first, then `on_context(event,
    selected_row_indices)` fires (the host's context menu). `set_data(..., row_fg=[...])` colours
    each row's text (severity colours)."""

    def __init__(self, parent, mode: str = "dark", editable: bool = False,
                 on_edit=None, raw_of=None, selectable: bool = False, on_context=None):
        super().__init__(parent)
        self._mode = mode
        self._columns: list = []
        self._rows: list = []
        self._widths: list = []
        self._redraw_job = None
        self._editable = editable
        self._on_edit = on_edit or (lambda *_a: False)
        self._raw_of = raw_of or (lambda r, c: self._rows[r][c] if c < len(self._rows[r]) else "")
        self._editbox: tk.Entry | None = None
        self._selectable = selectable
        self._on_context = on_context
        self._selected: set = set()          # VIEW positions (what's on screen); selection() maps to source
        self._anchor: int | None = None
        self._row_fg: list = []              # per-SOURCE-row text colours
        self._sort: tuple | None = None      # (col, 'asc'|'desc') - the header-click tri-state
        self._filters: list = []             # cascade filter specs ({col, text, regex, values})
        self._view: list = []                # visible SOURCE row indices, in display order
        self._click_col: int | None = None   # a header press outside a separator (sort on release)
        self._popup: tk.Toplevel | None = None

        family = theme.MONO_FONT[0]
        narrow = theme.narrow_family(self)
        self._font_normal = tkfont.Font(root=self, family=family, size=10)
        self._font_small = tkfont.Font(root=self, family=narrow, size=8)
        self._font_header = tkfont.Font(root=self, family=family, size=10, weight="bold")
        self._row_h = self._font_normal.metrics("linespace") + 8
        self._header_h = self._font_header.metrics("linespace") + 10

        self.chips = ttk.Frame(self)          # the active sort/filter chips (hidden while empty)
        self.header = tk.Canvas(self, highlightthickness=0, height=self._header_h)
        self.body = tk.Canvas(self, highlightthickness=0)
        vsb = ttk.Scrollbar(self, orient="vertical", command=self.body.yview)
        hsb = ttk.Scrollbar(self, orient="horizontal", command=self._xview_both)
        self.body.configure(yscrollcommand=lambda a, b: (vsb.set(a, b), self._schedule_redraw()),
                            xscrollcommand=hsb.set)
        self.chips.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.chips.grid_remove()
        self.header.grid(row=1, column=0, sticky="nsew")
        self.body.grid(row=2, column=0, sticky="nsew")
        vsb.grid(row=1, column=1, rowspan=2, sticky="ns")
        hsb.grid(row=3, column=0, sticky="ew")
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.body.bind("<MouseWheel>", self._on_wheel)
        self.body.bind("<Configure>", lambda _e: self._schedule_redraw())
        # the header: drag a separator to resize / double-click it to auto-fit; a plain click on a
        # column SORTS it (asc -> desc -> release); a right-click opens the column's filter popup.
        self._drag: tuple | None = None       # (col, press_x, width0) while a separator drag is live
        self.header.bind("<Motion>", self._header_hover)
        self.header.bind("<Leave>", lambda _e: self.header.configure(cursor=""))
        self.header.bind("<Button-1>", self._header_press)
        self.header.bind("<B1-Motion>", self._header_drag)
        self.header.bind("<ButtonRelease-1>", self._header_release)
        self.header.bind("<Double-Button-1>", self._header_dclick)
        self.header.bind("<Button-3>", self._header_filter_menu)
        if editable:
            self.body.bind("<Double-Button-1>", self._cell_dclick)
        if selectable:
            self.body.bind("<Button-1>", self._body_press)
            self.body.bind("<B1-Motion>", self._body_drag_select)
            self.body.bind("<Button-3>", self._body_context)
        self._apply_colors()

    # --- data ------------------------------------------------------------------------------------ #
    def set_data(self, columns, rows, row_fg=None) -> None:
        """Load the table: compute the data-adapted column widths, then draw the visible slice.
        `row_fg` optionally colours each row's text (a list of colours, None/'' = the theme fg).
        A new table resets the sort, the filters, and the selection."""
        self._close_editbox()
        self._close_popup()
        self._columns = [str(c) for c in columns]
        self._rows = [[sanitize(cell) for cell in row] for row in rows]
        self._row_fg = list(row_fg or [])
        self._sort, self._filters = None, []
        self._widths = compute_col_widths(
            self._columns, self._rows,
            self._font_normal.measure, self._font_small.measure, self._font_header.measure)
        self.body.yview_moveto(0)
        self._xview_both("moveto", 0)
        self._refresh_view()

    # --- sort + cascade filters (non-destructive: only the VIEW permutes/narrows) ------------------ #
    def _refresh_view(self) -> None:
        """Recompute the view (filters -> sort), drop the selection (the screen rows changed meaning),
        rebuild the chips, and redraw."""
        self._view = sorted_view(self._rows, apply_filters(self._rows, self._filters), self._sort)
        self._selected, self._anchor = set(), None
        self._update_chips()
        self.body.yview_moveto(0)
        self._apply_widths()

    def add_filter(self, spec: dict) -> None:
        """Append one cascade filter ({col, text, regex} or {col, values}) and narrow the view."""
        self._filters.append(spec)
        self._refresh_view()

    def remove_filter(self, index: int) -> None:
        if 0 <= index < len(self._filters):
            del self._filters[index]
            self._refresh_view()

    def clear_filters(self) -> None:
        """Release the sort AND every filter (the chips' Clear all)."""
        self._sort, self._filters = None, []
        self._refresh_view()

    def _filter_desc(self, spec: dict) -> str:
        name = self._columns[spec["col"]] if spec["col"] < len(self._columns) else f"col {spec['col']}"
        if spec.get("values") is not None:
            n = len(spec["values"])
            only = next(iter(spec["values"])) if n == 1 else None
            return f"{name} = {only!r}" if only is not None else f"{name} ∈ {n} values"
        return f"{name} ~ /{spec.get('text', '')}/" if spec.get("regex") else f"{name} : '{spec.get('text', '')}'"

    def _update_chips(self) -> None:
        """Rebuild the chips row: one chip per active sort/filter (click = remove it) + Clear all.
        Hidden entirely when nothing is active."""
        for child in self.chips.winfo_children():
            child.destroy()
        active = int(self._sort is not None) + len(self._filters)
        if not active:
            self.chips.grid_remove()
            return
        if self._sort is not None:
            col, direction = self._sort
            name = self._columns[col] if col < len(self._columns) else f"col {col}"
            arrow = "▲" if direction == "asc" else "▼"
            ttk.Button(self.chips, text=f"{name} {arrow}  ✕", style="Toolbutton",
                       command=lambda: (setattr(self, "_sort", None), self._refresh_view())
                       ).pack(side="left", padx=(2, 2), pady=1)
        for i, spec in enumerate(self._filters):
            ttk.Button(self.chips, text=f"{self._filter_desc(spec)}  ✕", style="Toolbutton",
                       command=lambda k=i: self.remove_filter(k)).pack(side="left", padx=2, pady=1)
        if active > 1:
            ttk.Button(self.chips, text="Clear all", style="Toolbutton",
                       command=self.clear_filters).pack(side="left", padx=(8, 2), pady=1)
        ttk.Label(self.chips, text=f"{len(self._view)} of {len(self._rows)} rows"
                  ).pack(side="right", padx=6)
        self.chips.grid()

    # --- row selection (selectable=True) ---------------------------------------------------------- #
    def selection(self) -> list:
        """The selected SOURCE row indices (into the rows passed to set_data), ascending - the host's
        data stays index-aligned no matter how the view is sorted/filtered."""
        return sorted(self._view[i] for i in self._selected if i < len(self._view))

    def _hit_row(self, event):
        """The VIEW position under the pointer (selection/anchor work in screen space)."""
        hit = cell_at(self._widths, self._row_h, len(self._view),
                      self.body.canvasx(event.x), self.body.canvasy(event.y))
        return None if hit is None else hit[0]

    def _body_press(self, event) -> None:
        row = self._hit_row(event)
        if row is None:
            return
        self._selected, self._anchor = updated_selection(
            self._selected, self._anchor, row,
            ctrl=bool(event.state & 0x0004), shift=bool(event.state & 0x0001))
        self._schedule_redraw()

    def _body_drag_select(self, event) -> None:
        """Click-drag extends the selection as a contiguous range from the press row (the anchor) to
        the row under the pointer - clamped to the table, so drifting off the columns or past the
        last row keeps extending instead of dropping the drag."""
        if self._anchor is None or not self._view:
            return
        row = int(self.body.canvasy(event.y) // self._row_h)
        row = max(0, min(len(self._view) - 1, row))
        lo, hi = sorted((self._anchor, row))
        new = set(range(lo, hi + 1))
        if new != self._selected:
            self._selected = new
            self._schedule_redraw()

    def _body_context(self, event) -> None:
        """Right-click: a click on an UNSELECTED row selects just it (the standard model), then the
        host's context menu fires over the whole selection."""
        row = self._hit_row(event)
        if row is not None and row not in self._selected:
            self._selected, self._anchor = {row}, row
            self._schedule_redraw()
        if self._on_context and self._selected:
            self._on_context(event, self.selection())

    def _apply_widths(self) -> None:
        """Sync the scroll regions to the current column widths and redraw (set_data + resizing)."""
        total_w = sum(self._widths) or 1
        total_h = max(1, len(self._view) * self._row_h)
        self.body.configure(scrollregion=(0, 0, total_w, total_h))
        self.header.configure(scrollregion=(0, 0, total_w, self._header_h))
        self._draw_header()
        self._schedule_redraw()

    # --- column resizing + sort + filter (the header) ---------------------------------------------- #
    def _col_at(self, x) -> int | None:
        """The column index under header canvas-x `x` (None past the last column)."""
        x0 = 0
        for i, width in enumerate(self._widths):
            if x0 <= x < x0 + width:
                return i
            x0 += width
        return None

    def _header_hover(self, event) -> None:
        on_edge = boundary_at(self._widths, self.header.canvasx(event.x)) is not None
        self.header.configure(cursor="sb_h_double_arrow" if on_edge else "")

    def _header_press(self, event) -> None:
        x = self.header.canvasx(event.x)
        col = boundary_at(self._widths, x)
        if col is not None:                    # on a separator -> a resize drag begins
            self._drag = (col, x, self._widths[col])
            self._click_col = None
        else:                                  # on a column -> a sort click (decided on release)
            self._drag = None
            self._click_col = self._col_at(x)

    def _header_release(self, _event) -> None:
        """A plain header click (no separator drag) cycles the column's sort: asc -> desc -> released."""
        if self._drag is None and self._click_col is not None:
            self._sort = cycle_sort(self._sort, self._click_col)
            self._refresh_view()
        self._drag = None
        self._click_col = None

    def _header_filter_menu(self, event) -> None:
        """Right-click a column header -> its cascade-filter popup."""
        col = self._col_at(self.header.canvasx(event.x))
        if col is None or not self._rows:
            return
        self._close_popup()
        self._popup = _FilterPopup(self, col, event.x_root, event.y_root)

    def _close_popup(self) -> None:
        if self._popup is not None:
            try:
                self._popup.destroy()
            except tk.TclError:
                pass
            self._popup = None

    def _header_drag(self, event) -> None:
        if self._drag is None:
            return
        self._click_col = None                 # a real drag is a resize, not a sort click
        col, x0, width0 = self._drag
        self._widths[col] = max(MIN_DRAG_W, int(width0 + self.header.canvasx(event.x) - x0))
        self._apply_widths()

    def _header_dclick(self, event) -> None:
        """Double-click a header separator: auto-fit that column to its content."""
        col = boundary_at(self._widths, self.header.canvasx(event.x))
        if col is None:
            return
        self._drag = None
        self._widths[col] = fit_col_width(self._columns, self._rows, col,
                                          self._font_normal.measure, self._font_small.measure,
                                          self._font_header.measure)
        self._apply_widths()

    # --- in-cell editing (editable=True) ----------------------------------------------------------- #
    def _cell_dclick(self, event) -> None:
        self._close_editbox()
        hit = cell_at(self._widths, self._row_h, len(self._view),
                      self.body.canvasx(event.x), self.body.canvasy(event.y))
        if hit is None:
            return
        view_row, col, x0 = hit
        src = self._view[view_row]                 # the host's raw_of/on_edit speak SOURCE indices
        raw = str(self._raw_of(src, col))
        if "\n" in raw:                            # a single-line Entry would destroy the other lines
            self.bell()
            return
        edit = tk.Entry(self.body, font=self._font_normal, relief="solid", borderwidth=1)
        edit.insert(0, raw)
        edit.select_range(0, "end")
        self.body.create_window(x0, view_row * self._row_h, window=edit, anchor="nw",
                                width=self._widths[col], height=self._row_h, tags="editbox")
        edit.focus_set()
        edit.bind("<Return>", lambda _e: self._commit_cell(src, col, edit.get()))
        edit.bind("<Escape>", lambda _e: self._close_editbox())
        edit.bind("<FocusOut>", lambda _e: self._close_editbox())
        self._editbox = edit

    def _commit_cell(self, row: int, col: int, value: str) -> None:
        """Enter in the cell editor: hand the new value to `on_edit`; on acceptance update the
        display copy and redraw."""
        self._close_editbox()
        if not self._on_edit(row, col, value):
            return
        while len(self._rows[row]) <= col:         # a ragged display row pads up to the edited cell
            self._rows[row].append("")
        self._rows[row][col] = sanitize(value)
        self._schedule_redraw()

    def _close_editbox(self) -> None:
        self.body.delete("editbox")
        if self._editbox is not None:
            try:
                self._editbox.destroy()
            except tk.TclError:
                pass
            self._editbox = None

    # --- scrolling ------------------------------------------------------------------------------- #
    def _xview_both(self, *args) -> None:
        self.body.xview(*args)
        self.header.xview(*args)

    def _on_wheel(self, event) -> None:
        self.body.yview_scroll(-1 * (event.delta // 120) * 3, "units")

    # --- drawing --------------------------------------------------------------------------------- #
    def _apply_colors(self) -> None:
        self._c_field = theme.TOKENS[self._mode]["field"]
        self._c_alt = theme.TOKENS[self._mode]["field_alt"]
        self._c_line = theme.TOKENS[self._mode]["grid_line"]
        self._c_fg = theme.TOKENS[self._mode]["fg"]
        self._c_head = theme.TOKENS[self._mode]["surface"]
        self._c_sel = theme.TOKENS[self._mode]["select_bg"]
        self._c_accent = theme.TOKENS[self._mode]["accent"]
        self.body.configure(bg=self._c_field)
        self.header.configure(bg=self._c_head)

    def set_theme(self, mode: str) -> None:
        self._mode = "dark" if mode == "dark" else "light"
        self._apply_colors()
        self._draw_header()
        self._schedule_redraw()

    def _schedule_redraw(self) -> None:
        """Coalesce scroll ticks into one idle redraw of the visible slice."""
        if self._redraw_job is None:
            self._redraw_job = self.after_idle(self._redraw)

    def _draw_header(self) -> None:
        self.header.delete("all")
        filtered = {spec["col"] for spec in self._filters}
        x = 0
        for c, (column, width) in enumerate(zip(self._columns, self._widths)):
            self.header.create_rectangle(x, 0, x + width, self._header_h,
                                         fill=self._c_head, outline=self._c_line)
            title = column
            if self._sort is not None and self._sort[0] == c:
                title += " ▲" if self._sort[1] == "asc" else " ▼"
            label = fit_text(title, width - 2 * _PAD_X, self._font_header.measure)
            fg = self._c_accent if c in filtered else self._c_fg   # a filtered column reads accented
            self.header.create_text(x + _PAD_X, self._header_h / 2, text=label,
                                    anchor="w", font=self._font_header, fill=fg)
            x += width

    def _redraw(self) -> None:
        self._redraw_job = None
        if not self.body.winfo_exists():
            return
        self.body.delete("cells")
        if not self._view or not self._widths:
            return
        row_h, widths = self._row_h, self._widths
        total_w = sum(widths)
        y_top = self.body.canvasy(0)
        y_bottom = y_top + self.body.winfo_height()
        first = max(0, int(y_top // row_h))
        last = min(len(self._view) - 1, int(y_bottom // row_h))
        # visible-column window (an x-scrolled wide table skips its off-screen columns)
        x_left = self.body.canvasx(0)
        x_right = x_left + self.body.winfo_width()
        for i in range(first, last + 1):                             # i = VIEW position
            src = self._view[i]
            y = i * row_h
            if i in self._selected:                                  # selection overrides the zebra
                fill = self._c_sel
            else:
                fill = self._c_alt if i % 2 else self._c_field       # zebra (by screen position)
            self.body.create_rectangle(0, y, total_w, y + row_h, fill=fill,
                                       outline="", tags="cells")
            row = self._rows[src]
            fg = (self._row_fg[src] if src < len(self._row_fg) and self._row_fg[src] else self._c_fg)
            x = 0
            for c, width in enumerate(widths):
                if x + width >= x_left and x <= x_right:
                    cell = row[c] if c < len(row) else ""
                    font = self._font_small if cell_kind(cell) == "small" else self._font_normal
                    if cell:
                        text = fit_text(cell, width - 2 * _PAD_X, font.measure)
                        self.body.create_text(x + _PAD_X, y + row_h / 2, text=text, anchor="w",
                                              font=font, fill=fg, tags="cells")
                x += width
            self.body.create_line(0, y + row_h, total_w, y + row_h,                # row border
                                  fill=self._c_line, tags="cells")
        x = 0
        for width in widths:                                                        # column borders
            x += width
            self.body.create_line(x, first * row_h, x, (last + 1) * row_h,
                                  fill=self._c_line, tags="cells")


class _FilterPopup(tk.Toplevel):
    """The right-click column filter (cascade): type a pattern (regex optional) OR pick values from
    the distinct list of the currently VISIBLE rows. Apply ADDS one filter (a removable chip above
    the header); Clear column drops every existing filter on this column."""

    def __init__(self, grid: DataGrid, col: int, x_root: int, y_root: int):
        super().__init__(grid)
        self._grid = grid
        self._col = col
        name = grid._columns[col] if col < len(grid._columns) else f"col {col}"
        self.title(f"Filter - {name}")
        self.transient(grid.winfo_toplevel())
        self.geometry(f"+{x_root}+{y_root}")
        self.resizable(False, False)

        body = ttk.Frame(self, padding=8)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=f"{name} - match text:").pack(anchor="w")
        self._text = ttk.Entry(body, width=34)
        self._text.pack(fill="x", pady=(2, 2))
        self._regex = tk.BooleanVar(value=False)
        ttk.Checkbutton(body, text="Regular expression", variable=self._regex).pack(anchor="w", pady=(0, 6))
        ttk.Label(body, text="or pick values (visible rows):").pack(anchor="w")
        wrap = ttk.Frame(body)
        wrap.pack(fill="both", expand=True)
        self._values = tk.Listbox(wrap, selectmode="extended", height=10, exportselection=False)
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=self._values.yview)
        self._values.configure(yscrollcommand=vsb.set)
        self._values.pack(side="left", fill="both", expand=True)
        vsb.pack(side="left", fill="y")
        self._distinct = distinct_values(grid._rows, grid._view, col)
        for value in self._distinct:
            self._values.insert("end", value if value != "" else "(blank)")
        c = theme.TOKENS[grid._mode]                 # theme the classic-Tk listbox from the tokens
        self._values.configure(background=c["field"], foreground=c["fg"],
                               selectbackground=c["select_bg"], selectforeground=c["select_fg"],
                               highlightthickness=0)

        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(buttons, text="Apply", command=self._apply).pack(side="left")
        ttk.Button(buttons, text="Clear column", command=self._clear_col).pack(side="left", padx=6)
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="left")
        self._text.focus_set()
        self.bind("<Return>", lambda _e: self._apply())
        self.bind("<Escape>", lambda _e: self.destroy())

    def _apply(self) -> None:
        """Picked values win over the pattern (they are the more explicit intent); empty both = no-op."""
        picked = [self._distinct[i] for i in self._values.curselection()]
        text = self._text.get().strip()
        if picked:
            self._grid.add_filter({"col": self._col, "values": set(picked)})
        elif text:
            self._grid.add_filter({"col": self._col, "text": text, "regex": bool(self._regex.get())})
        self.destroy()

    def _clear_col(self) -> None:
        self._grid._filters = [s for s in self._grid._filters if s["col"] != self._col]
        self._grid._refresh_view()
        self.destroy()
