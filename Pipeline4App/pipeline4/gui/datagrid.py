"""The shared READ-ONLY data grid (the Files-tab CSV/xlsx viewers + the Database Explorer results).

ttk.Treeview cannot draw cell gridlines on Tk 8.6 and its tags (fonts/colours) apply per ROW, never
per cell - so the user-requested look (grid borders, zebra rows, and a smaller NARROW font for cells
longer than LONG_CELL_CHARS) is drawn directly on a Canvas instead. VIRTUAL rendering: only the
visible row slice is drawn on each scroll tick, so a 2000-row result costs the same as a screenful.

Column widths ADAPT TO THE DATA: each column is sized to its widest sampled cell (measured in the
font that cell will actually use - a long cell measures in the small narrow font), clamped to
[MIN_COL_W, MAX_COL_W]; a cell wider than its column truncates with an ellipsis. The width/fit/font
rules are pure helpers (measure functions injected) so they are unit-testable without a display.
"""
from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

from pipeline4.gui import theme

LONG_CELL_CHARS = 64        # a cell longer than this renders in the small NARROW font
MIN_COL_W, MAX_COL_W = 60, 420
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


# --- the widget -------------------------------------------------------------------------------------- #
class DataGrid(ttk.Frame):
    """Header canvas + body canvas (x-scroll synced), gridlines, zebra rows, per-cell fonts."""

    def __init__(self, parent, mode: str = "dark"):
        super().__init__(parent)
        self._mode = mode
        self._columns: list = []
        self._rows: list = []
        self._widths: list = []
        self._redraw_job = None

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
        self._apply_colors()

    # --- data ------------------------------------------------------------------------------------ #
    def set_data(self, columns, rows) -> None:
        """Load the table: compute the data-adapted column widths, then draw the visible slice."""
        self._columns = [str(c) for c in columns]
        self._rows = [[sanitize(cell) for cell in row] for row in rows]
        self._widths = compute_col_widths(
            self._columns, self._rows,
            self._font_normal.measure, self._font_small.measure, self._font_header.measure)
        total_w = sum(self._widths) or 1
        total_h = max(1, len(self._rows) * self._row_h)
        self.body.configure(scrollregion=(0, 0, total_w, total_h))
        self.header.configure(scrollregion=(0, 0, total_w, self._header_h))
        self.body.yview_moveto(0)
        self._xview_both("moveto", 0)
        self._draw_header()
        self._schedule_redraw()

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
            fill = self._c_alt if i % 2 else self._c_field           # zebra
            self.body.create_rectangle(0, y, total_w, y + row_h, fill=fill,
                                       outline="", tags="cells")
            row = self._rows[i]
            x = 0
            for c, width in enumerate(widths):
                if x + width >= x_left and x <= x_right:
                    cell = row[c] if c < len(row) else ""
                    font = self._font_small if cell_kind(cell) == "small" else self._font_normal
                    if cell:
                        text = fit_text(cell, width - 2 * _PAD_X, font.measure)
                        self.body.create_text(x + _PAD_X, y + row_h / 2, text=text, anchor="w",
                                              font=font, fill=self._c_fg, tags="cells")
                x += width
            self.body.create_line(0, y + row_h, total_w, y + row_h,                # row border
                                  fill=self._c_line, tags="cells")
        x = 0
        for width in widths:                                                        # column borders
            x += width
            self.body.create_line(x, first * row_h, x, (last + 1) * row_h,
                                  fill=self._c_line, tags="cells")
