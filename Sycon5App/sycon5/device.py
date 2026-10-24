"""A slave (GSDML generic device) dialog: the Modules page.

Modules grid (`CModulesGrid`, auto id 321): header 18 px, rows 16 px (row n centre at y+26+16(n-1)); row 1 is
the DAP, then one row per module in slot order. 'Add Module' appends a row with the first GSDML module; the
row's Slot cell (x+60) opens a win32 ComboBox 1901, its Module cell (x+150) a ComboBox 1904 listing every module
of the GSDML - select by text through win32. A module row's submodule rows are hidden: double-click its glyph
(x+17); select a submodule row through the icon column (x+9).

Submodule details: the Dataset combo (311) enables for a selected submodule with parameters; 'Parameter' swaps
the IOs grid (322) for the `CParamGrid` (auto id 320): one row per record (expanded, Value = raw bytes), then
one row per parameter (~16 px rows, 4 visible). A double-click on a Value cell's text opens a win32 editor
(ctrl id 1902): an Edit (numbers, bits) or a ComboBox (enumerations); commit by a click on the row's Name cell.
"""
import time

import win32con
from pywinauto import keyboard, mouse
from pywinauto.win32structures import RECT

from .dialog import ConfigDialog
from .drawing import capture, text_bands
from .session import SyconError, log

MODULES_PAGE = "Modules"
MODULES_GRID_ID, PARAM_GRID_ID, IO_GRID_ID = "321", "320", "322"
DATASET_COMBO_ID, DISPLAY_COMBO_ID = 311, 312
SLOTS_TEXT_ID, DATA_LENGTH_TEXT_ID = 310, 293          # 'Use of slots: 2/2', 'State of data length: Input ...'
SLOT_COMBO_ID, MODULE_COMBO_ID, EDITOR_ID = 1901, 1904, 1902
ROW_Y0, ROW_H = 26, 16             # an 18 px header, 16 px rows (editor rectangles, 2026-10-23)
GLYPH_X, ICON_X, SLOT_X, MODULE_X, RIGHT_X = 17, 9, 60, 150, 560
PARAM_ROW_Y0, PARAM_ROW_H, PARAM_VALUE_X, PARAM_NAME_X = 25, 16, 395, 60
PARAM_VISIBLE_ROWS = 4


def row_y(n):
    return ROW_Y0 + ROW_H * (n - 1)


class DeviceDialog(ConfigDialog):
    # ---- Modules grid -------------------------------------------------------------------------------------
    _grid = None
    GRID_REF_W, PARAM_GRID_REF_W = 571, 561     # the grids' widths at the dialog's default size (the control maps)

    def modules_page(self):
        self.select_page(MODULES_PAGE)
        self._grid = self.pane(MODULES_GRID_ID).rectangle()
        return self._grid

    def sx(self, x):
        """A Modules-grid column offset measured at the reference width, scaled to the grid as shown (maximized)."""
        return int(round(x * self.grid_rect().width() / self.GRID_REF_W))

    def psx(self, x, r):
        """The same for the parameter grid."""
        return int(round(x * r.width() / self.PARAM_GRID_REF_W))

    def grid_rect(self):
        """The Modules grid rectangle, read once per page selection (every UIA descendants walk of the dialog
        costs about a second)."""
        if self._grid is None:
            self._grid = self.pane(MODULES_GRID_ID).rectangle()
        return self._grid

    def _static(self, cid):
        """The text of a win32 Static of the dialog by control id (fast; the UIA Text walk is slow)."""
        for c in self.w32.descendants(class_name="Static"):
            if c.control_id() == cid:
                return c.window_text()
        return ""

    def slots_used(self):
        t = self._static(SLOTS_TEXT_ID) or (self.texts("Use of slots") or [""])[0]
        if not t:
            raise SyconError("'Use of slots' text not found")
        return int(t.split(":")[1].split("/")[0])

    def _close_dropdowns(self):
        for c in self.controls(("ComboBox",)):
            c.send_message(win32con.CB_SHOWDROPDOWN, 0, 0)

    def add_module(self):
        """Append a module row; returns its row index (1 = DAP, so the new row is the new slot count)."""
        before = self.slots_used()
        for attempt in range(3):          # a first press only closes an open in-place editor
            self.press("Add Module", settle=1.2)
            after = self.slots_used()
            if after == before + 1:
                self.collapse_all()       # the new row may come expanded: slot n on row 1 + n only when none is
                return after
            log("  Add Module: slots still %d (attempt %d)" % (after, attempt + 1))
        raise SyconError("Add Module: slots %d -> %d" % (before, after))

    def _open_combo_on(self, y):
        """The in-place module combo when it is already open on the row at grid offset y (re-opening it cost a
        module its submodule, round 3)."""
        for cb in self.controls(("ComboBox",), cid=MODULE_COMBO_ID):
            rc = cb.rectangle()
            if abs((rc.top + rc.bottom) // 2 - y) <= ROW_H // 2 + 2:
                return cb
        return None

    def module_combo(self, row):
        for attempt in range(5):          # a first click may only close an editor left open on another cell
            if attempt == 3:              # a dialog on a freshly loaded project answered no click at 18:24: the
                self._grid = None         # grid rectangle read again, more time given
                self.select_page(MODULES_PAGE)
                time.sleep(1.5)
            r = self.grid_rect()
            y = r.top + row_y(row)
            cb = self._open_combo_on(y)
            if cb is not None:
                return cb
            mouse.click(coords=(r.left + self.sx(MODULE_X), y))
            time.sleep(1.0 if attempt < 3 else 2.0)
            cb = self.controls(("ComboBox",), cid=MODULE_COMBO_ID)
            if cb:
                return cb[0]
            log("  module cell of row %d: no combo yet (attempt %d, grid %s, rows %r)" % (
                row, attempt + 1, r, self.visible_rows()))
        raise SyconError("no module combo on row %d" % row)

    def set_module(self, row, text):
        """Choose the module of a row through its in-place combo (win32 select: the editor closes itself =
        committed), then make the row the current line through its icon column (no editor left open: the next
        'Add Module' needs that, and re-opening the combo for a read-back cost the module its submodule)."""
        cb = self.module_combo(row)
        current = cb.selected_text()
        if current != text:
            try:
                cb.select(text)
            except (IndexError, ValueError) as ex:
                self._close_dropdowns()
                raise SyconError("module %r not offered on row %d: %s" % (text, row, ex))
            time.sleep(1.0)
        else:
            self._close_dropdowns()
        self.select_row(row)
        log("  row %d module: %r -> %r" % (row, current, text))

    @staticmethod
    def _order_of(item):
        """'DI 16x24VDC ST V0.0  [6ES7 131-6BH01-0BA0]' -> '6ES7131-6BH01-0BA0'."""
        if "[" in item and item.endswith("]"):
            return item.rsplit("[", 1)[1][:-1].replace(" ", "").upper()
        return ""

    def resolve_module(self, row, spec):
        """The combo text for a module spec: the text itself, or 'order:<order number>' resolved against the
        combo's items (the first plain variant of that order number - no ', QI' / ', MSI' suffix - else the
        first)."""
        if not spec.startswith("order:"):
            return spec
        order = spec[6:].replace(" ", "").upper()
        cb = self.module_combo(row)
        items = cb.item_texts()
        self._close_dropdowns()
        matches = [it for it in items if self._order_of(it) == order]
        if not matches:
            raise SyconError("no module with order number %s among %d items (e.g. %r)" % (order, len(items), items[:3]))
        plain = [it for it in matches if "," not in it.rsplit("[", 1)[0]]
        return (plain or matches)[0]

    def set_slot(self, row, slot):
        r = self.grid_rect()
        mouse.click(coords=(r.left + self.sx(SLOT_X), r.top + row_y(row)))
        time.sleep(1.2)
        cb = self.controls(("ComboBox",), cid=SLOT_COMBO_ID)
        if not cb:
            raise SyconError("no slot combo on row %d" % row)
        if cb[0].selected_text() != str(slot):
            cb[0].select(str(slot))
            time.sleep(1.0)
        self._close_dropdowns()
        mouse.click(coords=(r.left + self.sx(RIGHT_X), r.top + row_y(row)))
        time.sleep(0.6)

    def expand_row(self, row):
        """Double-click the row's expand box (located by its pixels; GLYPH_X scaled as the fallback)."""
        r = self.grid_rect()
        _cols, has_box, centre = self._glyph_columns(row)
        x = centre if has_box else self.sx(GLYPH_X)
        mouse.double_click(coords=(r.left + x, r.top + row_y(row)))
        time.sleep(1.2)
        self._close_dropdowns()

    def select_row(self, row):
        r = self.grid_rect()
        mouse.click(coords=(r.left + ICON_X, r.top + row_y(row)))
        time.sleep(0.6)
        self._close_dropdowns()

    # ---- submodules (an AL1202's ports) -------------------------------------------------------------------
    # Probed 2026-10-23 17:05 (scripts/probe_submodules.py): the AL1202's `8 Ports` row (row 2) shows its
    # `IO-Link Master` sub row (row 3) from the start; 'Add Submodule' with the module row selected appends a
    # submodule row at the end with the NEXT subslot assigned by SYCON.net (2, 3, ...; its Sub Slot cell opens
    # no editor) and the first submodule of the GSDML preselected (`IO-Link In/Out 32/32 Byte + PQI`, 22 items,
    # the texts of the Fives tool verbatim); its Submodule cell (x+150) opens the in-place ComboBox 1904 like a
    # module row's. The grid shows 8 rows: the new row is found as the last text band after scrolling to the end.
    def visible_rows(self):
        """The visual row indices (1 = the first row under the header) that carry text."""
        return [y // ROW_H for y, n in text_bands(self.grid_rect(), ROW_H) if y >= ROW_H and n > 100]

    def data_length(self):
        return self._static(DATA_LENGTH_TEXT_ID) or (self.texts("State of data length") or [""])[0]

    def scroll_to_end(self, up=False):
        """Wheel the Modules grid down (up) until nothing shifts any more."""
        r = self.grid_rect()
        for _ in range(12):
            if self._scroll_pixels(r, -3 if up else 3) <= 0:
                return
        raise SyconError("the Modules grid keeps scrolling")

    def is_expanded(self, module_row, slots_used=None):
        """A module row is expanded when the grid shows more rows than the DAP + the modules (one module only)."""
        slots_used = slots_used if slots_used is not None else self.slots_used()
        return len(self.visible_rows()) > slots_used

    def row_expanded(self, row):
        """Whether THIS module row shows its submodule rows: its glyph is a '-' (expanded) or a '+' (collapsed,
        a vertical stroke in the box) - read from the pixels, since a double-click toggles (2026-10-23 18:34: a
        loaded project showed slot 1 expanded already and the blind toggle collapsed it)."""
        run, has_box, _centre = self._glyph_columns(row)
        if not has_box:
            return False
        core = run[1:-1] if len(run) >= 6 and run[0] >= 6 and run[-1] >= 6 else run   # the current row's box is black:
        return max(core) <= 3                                                          # its borders bracket the run
        # measured 18:56: grey '+' [1,1,5,1,1], grey '-' [1,1,1,1,1], black '+' [8,2,3,3,7,3,3,2,8], black '-' [8,2,3,3,3,3,3,2,8]

    def has_glyph(self, row):
        """A module row (the DAP too) carries an expand box; a submodule row does not."""
        return self._glyph_columns(row)[1]

    GLYPH_X0, GLYPH_X1 = 9, 24         # the expand box lies here; the row marker sits left of it, the Slot cell right

    def _glyph_columns(self, row):
        """The '+' / '-' strokes of the row's expand box, read from the pixels (dark < 300 per column over a
        13 px band): the horizontal stroke is a run of >= 4 columns with a dark pixel each, the '+' adds a
        column of >= 4 in its middle. The box border is black on the DAP row and light on a module row (18:50),
        so the strokes are what is looked for. Returns (the run's column counts, whether a box is there, the
        run centre's x offset)."""
        r = self.grid_rect()
        y = r.top + row_y(row)
        band = RECT(r.left + self.GLYPH_X0, y - 6, r.left + self.GLYPH_X1, y + 7)
        bits, stride, bpp, w, h = capture(band)
        cols = [sum(1 for yy in range(h) if sum(bits[yy * stride + x * bpp: yy * stride + x * bpp + 3]) < 300)
                for x in range(w)]
        inner = [min(n, 8) if n < h - 2 else 0 for n in cols]      # a full column is a border / grid line, not a stroke
        best, start = None, None
        for x, n in enumerate(inner + [0]):
            if n >= 1 and start is None:
                start = x
            elif n < 1 and start is not None:
                if x - start >= 4 and (best is None or x - start > best[1] - best[0]):
                    best = (start, x)
                start = None
        if best is None:
            return cols or [0], False, None
        run = inner[best[0]:best[1]]
        return run, True, self.GLYPH_X0 + (best[0] + best[1]) // 2

    def collapse_all(self):
        """Collapse every expanded module row (the DAP included) so that slot n sits on row 1 + n: SYCON.net
        reopens a dialog with the rows expanded as they were left (2026-10-23 18:42: slot 1 expanded, slot 7
        one row lower than expected)."""
        for _ in range(16):
            for k in self.visible_rows():
                if self.has_glyph(k) and self.row_expanded(k):
                    self.expand_row(k)
                    break
            else:
                return
        raise SyconError("the Modules grid keeps showing expanded rows")

    def ensure_expanded(self, row):
        """Show the module row's submodule rows: the glyph read first, the row count the proof (a double-click
        toggles; if it removed rows the row was expanded and is toggled back)."""
        if self.row_expanded(row):
            return
        before = self.visible_rows()
        self.expand_row(row)
        after = self.visible_rows()
        if self.row_expanded(row) or len(after) > len(before):
            return
        if len(after) < len(before):
            self.expand_row(row)
            log("  row %d: the glyph read collapsed (%r) but the double-click removed rows - toggled back" % (
                row, self._glyph_columns(row)))
            return
        raise SyconError("row %d did not expand (glyph columns %r, rows %r -> %r)" % (row, self._glyph_columns(row), before, after))

    def add_submodule(self, module_row):
        """Append a submodule row under the module (the module row must be expanded and selected); returns the
        visual row of the new submodule (the last row of the grid, scrolled into view)."""
        before = self.data_length()
        self.scroll_to_end(up=True)       # the module row at its unscrolled place
        self.select_row(module_row)
        for attempt in range(3):          # a first press only closes an open in-place editor
            self.press("Add Submodule", settle=1.2)
            if self.data_length() != before:
                break
            log("  Add Submodule: data length unchanged (attempt %d)" % (attempt + 1))
        else:
            raise SyconError("Add Submodule added nothing (data length %r)" % before)
        self.scroll_to_end()
        rows = self.visible_rows()
        if not rows:
            raise SyconError("no rows visible in the Modules grid after Add Submodule")
        return rows[-1]

    def set_submodule(self, row, text):
        """Choose a submodule row's submodule by text (spacing collapsed, case ignored) through the in-place combo."""
        cb = self.module_combo(row)
        items = cb.item_texts()
        match = [it for it in items if self.session.same_text(it, text)]
        if not match:
            self._close_dropdowns()
            raise SyconError("submodule %r not offered on row %d: %r" % (text, row, items))
        current = cb.selected_text()
        if current != match[0]:
            cb.select(match[0])
            time.sleep(1.0)
        else:
            self._close_dropdowns()
        self.select_row(row)
        log("  row %d submodule: %r -> %r" % (row, current, match[0]))
        return match[0]

    # ---- parameters ----------------------------------------------------------------------------------------
    def dataset(self, name="Parameter"):
        cb = self.combo(DATASET_COMBO_ID)
        if cb is None or not cb.is_enabled():
            raise SyconError("the Dataset combo is disabled: select a submodule row with parameters first")
        cb.select(name)
        time.sleep(2.0)
        grids = self.panes_of_class("CParamGrid")
        if not grids:
            raise SyconError("no parameter grid after Dataset = %s" % name)
        return grids[0].rectangle()

    def param_grid(self):
        grids = self.panes_of_class("CParamGrid")
        if not grids:
            raise SyconError("no parameter grid")
        return grids[0].rectangle()

    def _dark_profile(self, r):
        bits, stride, bpp, w, h = capture(r)
        prof = []
        for y in range(h):
            row = bits[y * stride:(y + 1) * stride]
            prof.append(sum(1 for x in range(40, w, 2) if (row[x * bpp] + row[x * bpp + 1] + row[x * bpp + 2]) < 600))
        return prof

    def _scroll_pixels(self, r, notches):
        """Scroll a grid by wheel notches (negative = up); returns the measured pixel shift of its text (0 when
        nothing moved)."""
        before = self._dark_profile(r)
        mouse.scroll(coords=(r.left + r.width() // 2, r.top + r.height() // 2), wheel_dist=-notches)
        time.sleep(1.0)
        after = self._dark_profile(r)
        if before == after:
            return 0
        best, best_err = 0, None
        for s in range(0, r.height() - 20):
            if notches >= 0:
                err = sum(abs(before[y + s] - after[y]) for y in range(18, r.height() - s))
            else:
                err = sum(abs(before[y] - after[y + s]) for y in range(18, r.height() - s))
            err = err / max(1, (r.height() - s - 18))
            if best_err is None or err < best_err:
                best, best_err = s, err
        return best

    _value_x = None

    def open_param_editor_at(self, y, r=None):
        """Double-click the Value cell of the parameter row at grid offset y; returns its win32 editor. The
        Value column's place is not proportional to the grid width (the measured 395 of 561 landed on 'Data
        type' in a maximized dialog, 18:58), so a few fractions of the width are tried and the one that opens
        an editor is kept for the dialog."""
        r = r or self.param_grid()
        candidates = [self._value_x] if self._value_x is not None else []
        candidates += [self.psx(PARAM_VALUE_X, r)] + [int(r.width() * f) for f in (0.55, 0.47, 0.62, 0.40)]
        tried = []
        for x in candidates:
            if x in tried:
                continue
            tried.append(x)
            mouse.double_click(coords=(r.left + x, r.top + y))
            time.sleep(1.2)
            eds = self.controls(("Edit", "ComboBox"), cid=EDITOR_ID)
            if eds:
                self._value_x = x
                return eds[0]
        raise SyconError("no value editor on the parameter row at y=%d (x tried %r of width %d)" % (y, tried, r.width()))

    def open_param_editor(self, visual_row, r=None):
        y = PARAM_ROW_Y0 + PARAM_ROW_H * visual_row
        return self.open_param_editor_at(y, r), y

    def set_param_at_y(self, y, value, r=None, what=""):
        """Set the Value of the parameter row at grid offset y (a combo item matched with its spacing collapsed
        and case ignored, or text typed into an Edit); the editor is re-opened to read the value back."""
        r = r or self.param_grid()
        ed = self.open_param_editor_at(y, r)
        kind = ed.class_name()
        want = str(value)
        if kind == "ComboBox":
            items = ed.item_texts()
            match = [it for it in items if self.session.same_text(it, value)]
            if not match:
                self._close_dropdowns()
                raise SyconError("value %r not among %r" % (value, items))
            want = match[0]
            if ed.selected_text() != want:
                ed.select(want)
                time.sleep(0.8)
        else:
            ed.select()
            time.sleep(0.2)
            keyboard.send_keys(str(value), with_spaces=True)
            time.sleep(0.3)
        mouse.click(coords=(r.left + self.psx(PARAM_NAME_X, r), r.top + y))     # commit: the row's Name cell
        time.sleep(0.8)
        ed2 = self.open_param_editor_at(y, r)
        shown = ed2.selected_text() if ed2.class_name() == "ComboBox" else ed2.window_text()
        self._close_dropdowns()
        mouse.click(coords=(r.left + self.psx(PARAM_NAME_X, r), r.top + y))
        time.sleep(0.6)
        log("  parameter %s(%s): -> %r" % (what, kind, shown))
        if str(shown) != want:
            raise SyconError("parameter reads %r after writing %r" % (shown, want))
        return shown

    def set_param_visual(self, visual_row, value, r=None):
        """Set the Value of the parameter shown on visual row v (0 = the first row of the grid)."""
        return self.set_param_at_y(PARAM_ROW_Y0 + PARAM_ROW_H * visual_row, value, r, "visual row %d " % visual_row)

    def param_rows_y(self, r=None):
        """The centre y (grid offsets) of the text rows of the parameter grid below its header, from the
        dark-pixel profile (alignment-free: the wheel may leave the rows anywhere)."""
        r = r or self.param_grid()
        prof = self._dark_profile(r)
        rows, start = [], None
        for y, n in enumerate(prof + [0]):
            if n > 3 and start is None:
                start = y
            elif n <= 3 and start is not None:
                if y - start >= 6 and start > 18:
                    rows.append((start + y) // 2)
                start = None
        return rows

    def scroll_param_grid_to_end(self, r=None):
        r = r or self.param_grid()
        for _ in range(40):
            if self._scroll_pixels(r, 3) <= 0:
                return
        raise SyconError("the parameter grid keeps scrolling")

    def set_last_param(self, value):
        """Set the LAST parameter row of the grid (an ET200SP module's `Potential group`, the one parameter of
        its last record): the grid wheeled to its end, the last text row located by its pixels."""
        r = self.param_grid()
        self.scroll_param_grid_to_end(r)
        ys = self.param_rows_y(r)
        if not ys:
            raise SyconError("no parameter rows visible at the end of the grid")
        return self.set_param_at_y(ys[-1], value, r, "last row ")

    def set_parameters(self, values):
        """values: {parameter index within the record (0 = its first parameter): value}. The record row is
        visual row 0, parameter i is visual row i + 1 before scrolling; rows beyond the 4 visible ones are reached
        by wheel scrolling with the pixel shift measured each time."""
        r = self.param_grid()
        visible = max(1, (r.height() - PARAM_ROW_Y0 - 4) // PARAM_ROW_H)     # 4 at the reference size, ~17 maximized
        scrolled_px = 0
        for index in sorted(values):
            target_px = PARAM_ROW_H * (index + 1)              # top of the wanted row, unscrolled
            while target_px - scrolled_px > PARAM_ROW_H * (visible - 1):
                shift = self._scroll_pixels(r, 1)
                if shift <= 0:
                    break                                      # nothing to scroll: every row is on show
                scrolled_px += shift
            visual = round((target_px - scrolled_px) / PARAM_ROW_H)
            if visual < 0 or visual > visible:
                raise SyconError("parameter %d not reachable (visual row %d of %d)" % (index, visual, visible))
            self.set_param_visual(visual, values[index], r)
