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

    def modules_page(self):
        self.select_page(MODULES_PAGE)
        self._grid = self.pane(MODULES_GRID_ID).rectangle()
        return self._grid

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
        r = self.grid_rect()
        y = r.top + row_y(row)
        for attempt in range(3):          # a first click may only close an editor left open on another cell
            cb = self._open_combo_on(y)
            if cb is not None:
                return cb
            mouse.click(coords=(r.left + MODULE_X, y))
            time.sleep(1.0)
            cb = self.controls(("ComboBox",), cid=MODULE_COMBO_ID)
            if cb:
                return cb[0]
            log("  module cell of row %d: no combo yet (attempt %d)" % (row, attempt + 1))
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
        mouse.click(coords=(r.left + SLOT_X, r.top + row_y(row)))
        time.sleep(1.2)
        cb = self.controls(("ComboBox",), cid=SLOT_COMBO_ID)
        if not cb:
            raise SyconError("no slot combo on row %d" % row)
        if cb[0].selected_text() != str(slot):
            cb[0].select(str(slot))
            time.sleep(1.0)
        self._close_dropdowns()
        mouse.click(coords=(r.left + RIGHT_X, r.top + row_y(row)))
        time.sleep(0.6)

    def expand_row(self, row):
        r = self.grid_rect()
        mouse.double_click(coords=(r.left + GLYPH_X, r.top + row_y(row)))
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
        """A module row is expanded when the grid shows more rows than the DAP + the modules."""
        slots_used = slots_used if slots_used is not None else self.slots_used()
        return len(self.visible_rows()) > slots_used

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

    def open_param_editor(self, visual_row, r=None):
        r = r or self.param_grid()
        y = PARAM_ROW_Y0 + PARAM_ROW_H * visual_row
        mouse.double_click(coords=(r.left + PARAM_VALUE_X, r.top + y))
        time.sleep(1.2)
        eds = self.controls(("Edit", "ComboBox"), cid=EDITOR_ID)
        if not eds:
            raise SyconError("no value editor on visual row %d" % visual_row)
        return eds[0], y

    def set_param_visual(self, visual_row, value, r=None):
        """Set the Value of the parameter shown on visual row v (0 = the first row of the grid)."""
        r = r or self.param_grid()
        ed, y = self.open_param_editor(visual_row, r)
        kind = ed.class_name()
        if kind == "ComboBox":
            items = ed.item_texts()
            if value not in items:
                self._close_dropdowns()
                raise SyconError("value %r not among %r" % (value, items))
            if ed.selected_text() != value:
                ed.select(value)
                time.sleep(0.8)
        else:
            ed.select()
            time.sleep(0.2)
            keyboard.send_keys(str(value), with_spaces=True)
            time.sleep(0.3)
        mouse.click(coords=(r.left + PARAM_NAME_X, r.top + y))     # commit: the row's Name cell
        time.sleep(0.8)
        ed2, _ = self.open_param_editor(visual_row, r)
        shown = ed2.selected_text() if ed2.class_name() == "ComboBox" else ed2.window_text()
        self._close_dropdowns()
        mouse.click(coords=(r.left + PARAM_NAME_X, r.top + y))
        time.sleep(0.6)
        log("  parameter visual row %d (%s): -> %r" % (visual_row, kind, shown))
        if str(shown) != str(value):
            raise SyconError("parameter reads %r after writing %r" % (shown, value))

    def set_parameters(self, values):
        """values: {parameter index within the record (0 = its first parameter): value}. The record row is
        visual row 0, parameter i is visual row i + 1 before scrolling; rows beyond the 4 visible ones are reached
        by wheel scrolling with the pixel shift measured each time."""
        r = self.param_grid()
        scrolled_px = 0
        for index in sorted(values):
            target_px = PARAM_ROW_H * (index + 1)              # top of the wanted row, unscrolled
            while target_px - scrolled_px > PARAM_ROW_H * (PARAM_VISIBLE_ROWS - 1):
                shift = self._scroll_pixels(r, 1)
                if shift <= 0:
                    raise SyconError("the parameter grid did not scroll")
                scrolled_px += shift
            visual = round((target_px - scrolled_px) / PARAM_ROW_H)
            if visual < 0 or visual >= PARAM_VISIBLE_ROWS + 1:
                raise SyconError("parameter %d not reachable (visual row %d)" % (index, visual))
            self.set_param_visual(visual, values[index], r)
