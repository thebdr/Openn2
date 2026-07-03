"""The Tk shell over `tableviewer.core`: a canvas data grid - gridlines, zebra rows, per-cell fonts
(long cells drop to a small narrow font), VIRTUAL rendering (only the visible slice draws, so row
count barely matters), data-adapted column widths with drag / double-click-fit resizing.

Header CLICK = tri-state natural sort; header RIGHT-CLICK = the cascade filter popup (substring /
regex / pick-list of the visible rows' distinct values, with the column's stats footer). Active
sort/filters show as removable CHIPS above the header. Ctrl+F = the global QUICK SEARCH (any cell,
live, a removable chip). Ctrl+C = copy the selection (or the whole filtered view) as TSV.
Double-click = in-place cell edit (`editable=True`) or the full ROW DETAIL popup (read-only grids).
`selectable=True` = row multi-select (click / Ctrl / Shift / drag) + `on_context` for a host menu.

Everything stateful reads `tableviewer.theme` at call time, so an embedder can rebind the palette
and fonts (see theme.py). ttk.Treeview can't do per-cell fonts or gridlines on Tk 8.6 - hence the
canvas."""
from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

from . import core, theme
from .core import (PAD_X, MIN_DRAG_W, boundary_at, cell_at, cell_kind, compute_col_widths,
                   cycle_sort, distinct_values, fit_col_width, fit_text, sanitize, sorted_view,
                   updated_selection)


class DataGrid(ttk.Frame):
    """See the module docstring. With `editable=True` a DATA cell edits in place on double-click
    (Enter commits through `on_edit(src_row, col, new) -> bool`); `raw_of(src_row, col)` supplies
    the underlying value (the grid itself only holds sanitized DISPLAY text). `set_data(...,
    row_fg=[...])` colours each row's text. `selection()`/`raw_of`/`on_edit` speak SOURCE indices,
    so hosts are sort/filter-agnostic."""

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
        # the default raw accessor reads the UNSANITIZED copy set_data keeps (multi-line cells show
        # whole in the row-detail card); a host with its own backing store overrides via raw_of.
        self._raw_rows: list = []
        self._raw_of = raw_of or (lambda r, c: self._raw_rows[r][c]
                                  if r < len(self._raw_rows) and c < len(self._raw_rows[r]) else "")
        self._editbox: tk.Entry | None = None
        self._selectable = selectable
        self._on_context = on_context
        self._selected: set = set()          # VIEW positions (what's on screen); selection() maps to source
        self._anchor: int | None = None
        self._row_fg: list = []              # per-SOURCE-row text colours
        self._sort: tuple | None = None      # (col, 'asc'|'desc') - the header-click tri-state
        self._filters: list = []             # cascade filter specs ({col, text, regex, values})
        self._quick: str = ""                # the global quick search (Ctrl+F; col=None spec)
        self._view: list = []                # visible SOURCE row indices, in display order
        self._click_col: int | None = None   # a header press outside a separator (sort on release)
        self._popup: tk.Toplevel | None = None

        family = theme.mono_family(self)
        narrow = theme.narrow_family(self)
        self._font_normal = tkfont.Font(root=self, family=family, size=10)
        self._font_small = tkfont.Font(root=self, family=narrow, size=8)
        self._font_header = tkfont.Font(root=self, family=family, size=10, weight="bold")
        self._row_h = self._font_normal.metrics("linespace") + 8
        self._header_h = self._font_header.metrics("linespace") + 10

        self.chips = ttk.Frame(self)          # the active sort/filter chips (hidden while empty)
        self.header = tk.Canvas(self, highlightthickness=0, height=self._header_h)
        self.body = tk.Canvas(self, highlightthickness=0, takefocus=1)
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
        else:
            self.body.bind("<Double-Button-1>", self._row_detail)
        if selectable:
            self.body.bind("<Button-1>", self._body_press)
            self.body.bind("<B1-Motion>", self._body_drag_select)
            self.body.bind("<Button-3>", self._body_context)
        # the keyboard surface: a click focuses the body so Ctrl+F / Ctrl+C reach the grid
        self.body.bind("<Button-1>", lambda _e: self.body.focus_set(), add="+")
        self.body.bind("<Control-f>", lambda _e: self.open_quick_search())
        self.body.bind("<Control-c>", lambda _e: self.copy_view())
        self._apply_colors()

    # --- data ------------------------------------------------------------------------------------ #
    def set_data(self, columns, rows, row_fg=None) -> None:
        """Load the table: compute the data-adapted column widths, then draw the visible slice.
        `row_fg` optionally colours each row's text (a list of colours, None/'' = the theme fg).
        A new table resets the sort, the filters, the quick search, and the selection."""
        self._close_editbox()
        self._close_popup()
        self._columns = [str(c) for c in columns]
        self._rows = [[sanitize(cell) for cell in row] for row in rows]
        self._raw_rows = [["" if cell is None else str(cell) for cell in row] for row in rows]
        self._row_fg = list(row_fg or [])
        self._sort, self._filters, self._quick = None, [], ""
        self._widths = compute_col_widths(
            self._columns, self._rows,
            self._font_normal.measure, self._font_small.measure, self._font_header.measure)
        self.body.yview_moveto(0)
        self._xview_both("moveto", 0)
        self._refresh_view()

    # --- sort + cascade filters + quick search (non-destructive: only the VIEW changes) ------------ #
    def active_filters(self) -> list:
        """The quick-search spec (col None) + the column filters, in application order."""
        quick = [{"col": None, "text": self._quick}] if self._quick else []
        return quick + self._filters

    def _refresh_view(self) -> None:
        """Recompute the view (filters -> sort), drop the selection (the screen rows changed meaning),
        rebuild the chips, and redraw."""
        self._view = sorted_view(self._rows, core.apply_filters(self._rows, self.active_filters()),
                                 self._sort)
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
        """Release the sort, every filter AND the quick search (the chips' Clear all)."""
        self._sort, self._filters, self._quick = None, [], ""
        self._refresh_view()

    def quick_search(self, text: str) -> None:
        """Set/clear the GLOBAL quick search (matches any cell, case-insensitive substring)."""
        self._quick = str(text or "").strip()
        self._refresh_view()

    def open_quick_search(self) -> None:
        """Ctrl+F: the small live quick-search box (Escape clears + closes)."""
        self._close_popup()
        self._popup = _QuickSearch(self)

    def copy_view(self) -> None:
        """Ctrl+C: the SELECTED rows (view order) - or the whole filtered view when nothing is
        selected - to the clipboard as TSV (pastes into Excel as cells)."""
        if self._selectable and self._selected:
            picked = [self._view[i] for i in sorted(self._selected) if i < len(self._view)]
        else:
            picked = list(self._view)
        if not picked:
            return
        self.clipboard_clear()
        self.clipboard_append(core.to_tsv(self._columns, self._rows, picked))

    def _filter_desc(self, spec: dict) -> str:
        col = spec.get("col")
        name = "*" if col is None else (self._columns[col] if col < len(self._columns) else f"col {col}")
        if spec.get("values") is not None:
            n = len(spec["values"])
            only = next(iter(spec["values"])) if n == 1 else None
            return f"{name} = {only!r}" if only is not None else f"{name} ∈ {n} values"
        return f"{name} ~ /{spec.get('text', '')}/" if spec.get("regex") else f"{name} : '{spec.get('text', '')}'"

    def _update_chips(self) -> None:
        """Rebuild the chips row: one chip per active sort/filter/quick-search (click = remove it)
        + Clear all. Hidden entirely when nothing is active."""
        for child in self.chips.winfo_children():
            child.destroy()
        active = int(self._sort is not None) + len(self._filters) + int(bool(self._quick))
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
        if self._quick:
            ttk.Button(self.chips, text=f"{self._filter_desc({'col': None, 'text': self._quick})}  ✕",
                       style="Toolbutton", command=lambda: self.quick_search("")
                       ).pack(side="left", padx=2, pady=1)
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

    # --- in-cell editing (editable=True) / row detail (read-only) ---------------------------------- #
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

    def _row_detail(self, event) -> None:
        """Double-click on a read-only grid: the full row as a vertical name/value card (wide tables
        read badly horizontally; the card shows every cell whole, multi-line values included)."""
        row = self._hit_row(event)
        if row is None:
            return
        self._close_popup()
        self._popup = _DetailPopup(self, self._view[row], event.x_root, event.y_root)

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
        tokens = theme.TOKENS[self._mode]
        self._c_field = tokens["field"]
        self._c_alt = tokens["field_alt"]
        self._c_line = tokens["grid_line"]
        self._c_fg = tokens["fg"]
        self._c_head = tokens["surface"]
        self._c_sel = tokens["select_bg"]
        self._c_accent = tokens["accent"]
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
            label = fit_text(title, width - 2 * PAD_X, self._font_header.measure)
            fg = self._c_accent if c in filtered else self._c_fg   # a filtered column reads accented
            self.header.create_text(x + PAD_X, self._header_h / 2, text=label,
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
                        text = fit_text(cell, width - 2 * PAD_X, font.measure)
                        self.body.create_text(x + PAD_X, y + row_h / 2, text=text, anchor="w",
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
    the distinct list of the currently VISIBLE rows, with the column's STATS as the footer. Apply
    ADDS one filter (a removable chip above the header); Clear column drops every existing filter
    on this column."""

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
        stats = core.stats_text(core.column_stats(grid._rows, grid._view, col))
        ttk.Label(body, text=stats, foreground=c["disabled_fg"]).pack(anchor="w", pady=(6, 0))

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


class _QuickSearch(tk.Toplevel):
    """The Ctrl+F box: one entry, LIVE global filtering (any cell, case-insensitive substring).
    Escape clears the search and closes; closing the box keeps the search (its chip removes it)."""

    def __init__(self, grid: DataGrid):
        super().__init__(grid)
        self._grid = grid
        self.title("Quick search")
        self.transient(grid.winfo_toplevel())
        self.resizable(False, False)
        top = grid.winfo_toplevel()
        self.geometry(f"+{top.winfo_rootx() + max(0, top.winfo_width() - 320)}+{top.winfo_rooty() + 60}")
        body = ttk.Frame(self, padding=8)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Search all columns:").pack(anchor="w")
        self._text = ttk.Entry(body, width=32)
        self._text.insert(0, grid._quick)
        self._text.pack(fill="x", pady=(2, 0))
        self._text.focus_set()
        self._text.icursor("end")
        self._text.bind("<KeyRelease>", lambda _e: self._grid.quick_search(self._text.get()))
        self.bind("<Escape>", lambda _e: (self._grid.quick_search(""), self.destroy()))
        self.bind("<Return>", lambda _e: self.destroy())


class _DetailPopup(tk.Toplevel):
    """The row-detail card (double-click on a read-only grid): every column NAME + its FULL raw
    value, vertically - wide tables read badly sideways; here multi-line cells show whole and the
    text is selectable/copyable."""

    def __init__(self, grid: DataGrid, src: int, x_root: int, y_root: int):
        super().__init__(grid)
        self.title(f"Row {src + 1}")
        self.transient(grid.winfo_toplevel())
        self.geometry(f"560x420+{x_root}+{y_root}")
        c = theme.TOKENS[grid._mode]
        wrap = ttk.Frame(self, padding=6)
        wrap.pack(fill="both", expand=True)
        text = tk.Text(wrap, wrap="word", relief="flat", background=c["field"], foreground=c["fg"],
                       insertbackground=c["fg"], padx=8, pady=6,
                       font=(theme.mono_family(self), 10))
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=vsb.set)
        text.pack(side="left", fill="both", expand=True)
        vsb.pack(side="left", fill="y")
        text.tag_configure("name", foreground=c["accent"],
                           font=(theme.mono_family(self), 10, "bold"))
        for col, name in enumerate(grid._columns):
            value = str(grid._raw_of(src, col))
            text.insert("end", f"{name}\n", "name")
            text.insert("end", (value if value != "" else "(blank)") + "\n\n")
        text.configure(state="disabled")             # read-only but still selectable/copyable
        self.bind("<Escape>", lambda _e: self.destroy())
