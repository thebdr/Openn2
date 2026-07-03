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
but FIT_MAX_W, no sampling). The width/fit/font/boundary rules are pure helpers (measure functions
injected) so they are unit-testable without a display.
"""
from __future__ import annotations

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
    With `selectable=True` rows MULTI-select (click / Ctrl-toggle / Shift-range); a right-click on
    an unselected row selects it first, then `on_context(event, selected_row_indices)` fires (the
    host's context menu). `set_data(..., row_fg=[...])` colours each row's text (severity colours)."""

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
        self._selected: set = set()
        self._anchor: int | None = None
        self._row_fg: list = []

        family = theme.MONO_FONT[0]
        narrow = theme.narrow_family(self)
        self._font_normal = tkfont.Font(root=self, family=family, size=10)
        self._font_small = tkfont.Font(root=self, family=narrow, size=8)
        self._font_header = tkfont.Font(root=self, family=family, size=10, weight="bold")
        self._row_h = self._font_normal.metrics("linespace") + 8
        self._header_h = self._font_header.metrics("linespace") + 10

        self.header = tk.Canvas(self, highlightthickness=0, height=self._header_h)
        self.body = tk.Canvas(self, highlightthickness=0)
        vsb = ttk.Scrollbar(self, orient="vertical", command=self.body.yview)
        hsb = ttk.Scrollbar(self, orient="horizontal", command=self._xview_both)
        self.body.configure(yscrollcommand=lambda a, b: (vsb.set(a, b), self._schedule_redraw()),
                            xscrollcommand=hsb.set)
        self.header.grid(row=0, column=0, sticky="nsew")
        self.body.grid(row=1, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, rowspan=2, sticky="ns")
        hsb.grid(row=2, column=0, sticky="ew")
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.body.bind("<MouseWheel>", self._on_wheel)
        self.body.bind("<Configure>", lambda _e: self._schedule_redraw())
        # column resize on the header: drag a separator; double-click it to auto-fit the column
        self._drag: tuple | None = None       # (col, press_x, width0) while a separator drag is live
        self.header.bind("<Motion>", self._header_hover)
        self.header.bind("<Leave>", lambda _e: self.header.configure(cursor=""))
        self.header.bind("<Button-1>", self._header_press)
        self.header.bind("<B1-Motion>", self._header_drag)
        self.header.bind("<ButtonRelease-1>", lambda _e: setattr(self, "_drag", None))
        self.header.bind("<Double-Button-1>", self._header_dclick)
        if editable:
            self.body.bind("<Double-Button-1>", self._cell_dclick)
        if selectable:
            self.body.bind("<Button-1>", self._body_press)
            self.body.bind("<Button-3>", self._body_context)
        self._apply_colors()

    # --- data ------------------------------------------------------------------------------------ #
    def set_data(self, columns, rows, row_fg=None) -> None:
        """Load the table: compute the data-adapted column widths, then draw the visible slice.
        `row_fg` optionally colours each row's text (a list of colours, None/'' = the theme fg);
        the selection is cleared (the row indices no longer mean the same rows)."""
        self._close_editbox()
        self._columns = [str(c) for c in columns]
        self._rows = [[sanitize(cell) for cell in row] for row in rows]
        self._row_fg = list(row_fg or [])
        self._selected, self._anchor = set(), None
        self._widths = compute_col_widths(
            self._columns, self._rows,
            self._font_normal.measure, self._font_small.measure, self._font_header.measure)
        self.body.yview_moveto(0)
        self._xview_both("moveto", 0)
        self._apply_widths()

    # --- row selection (selectable=True) ---------------------------------------------------------- #
    def selection(self) -> list:
        """The selected row indices, ascending."""
        return sorted(self._selected)

    def _hit_row(self, event):
        hit = cell_at(self._widths, self._row_h, len(self._rows),
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
        total_h = max(1, len(self._rows) * self._row_h)
        self.body.configure(scrollregion=(0, 0, total_w, total_h))
        self.header.configure(scrollregion=(0, 0, total_w, self._header_h))
        self._draw_header()
        self._schedule_redraw()

    # --- column resizing (header separators) ------------------------------------------------------ #
    def _header_hover(self, event) -> None:
        on_edge = boundary_at(self._widths, self.header.canvasx(event.x)) is not None
        self.header.configure(cursor="sb_h_double_arrow" if on_edge else "")

    def _header_press(self, event) -> None:
        x = self.header.canvasx(event.x)
        col = boundary_at(self._widths, x)
        self._drag = (col, x, self._widths[col]) if col is not None else None

    def _header_drag(self, event) -> None:
        if self._drag is None:
            return
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
        hit = cell_at(self._widths, self._row_h, len(self._rows),
                      self.body.canvasx(event.x), self.body.canvasy(event.y))
        if hit is None:
            return
        row, col, x0 = hit
        raw = str(self._raw_of(row, col))
        if "\n" in raw:                            # a single-line Entry would destroy the other lines
            self.bell()
            return
        edit = tk.Entry(self.body, font=self._font_normal, relief="solid", borderwidth=1)
        edit.insert(0, raw)
        edit.select_range(0, "end")
        self.body.create_window(x0, row * self._row_h, window=edit, anchor="nw",
                                width=self._widths[col], height=self._row_h, tags="editbox")
        edit.focus_set()
        edit.bind("<Return>", lambda _e: self._commit_cell(row, col, edit.get()))
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
        x = 0
        for column, width in zip(self._columns, self._widths):
            self.header.create_rectangle(x, 0, x + width, self._header_h,
                                         fill=self._c_head, outline=self._c_line)
            label = fit_text(column, width - 2 * _PAD_X, self._font_header.measure)
            self.header.create_text(x + _PAD_X, self._header_h / 2, text=label,
                                    anchor="w", font=self._font_header, fill=self._c_fg)
            x += width

    def _redraw(self) -> None:
        self._redraw_job = None
        if not self.body.winfo_exists():
            return
        self.body.delete("cells")
        if not self._rows or not self._widths:
            return
        row_h, widths = self._row_h, self._widths
        total_w = sum(widths)
        y_top = self.body.canvasy(0)
        y_bottom = y_top + self.body.winfo_height()
        first = max(0, int(y_top // row_h))
        last = min(len(self._rows) - 1, int(y_bottom // row_h))
        # visible-column window (an x-scrolled wide table skips its off-screen columns)
        x_left = self.body.canvasx(0)
        x_right = x_left + self.body.winfo_width()
        for i in range(first, last + 1):
            y = i * row_h
            if i in self._selected:                                  # selection overrides the zebra
                fill = self._c_sel
            else:
                fill = self._c_alt if i % 2 else self._c_field       # zebra
            self.body.create_rectangle(0, y, total_w, y + row_h, fill=fill,
                                       outline="", tags="cells")
            row = self._rows[i]
            fg = (self._row_fg[i] if i < len(self._row_fg) and self._row_fg[i] else self._c_fg)
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
