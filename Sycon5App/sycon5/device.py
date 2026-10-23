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
from .drawing import capture
from .session import SyconError, log

MODULES_PAGE = "Modules"
MODULES_GRID_ID, PARAM_GRID_ID, IO_GRID_ID = "321", "320", "322"
DATASET_COMBO_ID, DISPLAY_COMBO_ID = 311, 312
SLOT_COMBO_ID, MODULE_COMBO_ID, EDITOR_ID = 1901, 1904, 1902
ROW_Y0, ROW_H = 26, 16             # an 18 px header, 16 px rows (editor rectangles, 2026-10-23)
GLYPH_X, ICON_X, SLOT_X, MODULE_X, RIGHT_X = 17, 9, 60, 150, 560
PARAM_ROW_Y0, PARAM_ROW_H, PARAM_VALUE_X, PARAM_NAME_X = 25, 16, 395, 60
PARAM_VISIBLE_ROWS = 4


def row_y(n):
    return ROW_Y0 + ROW_H * (n - 1)


class DeviceDialog(ConfigDialog):
    # ---- Modules grid -------------------------------------------------------------------------------------
    def modules_page(self):
        self.select_page(MODULES_PAGE)
        return self.pane(MODULES_GRID_ID).rectangle()

    def slots_used(self):
        t = self.texts("Use of slots")
        if not t:
            raise SyconError("'Use of slots' text not found")
        return int(t[0].split(":")[1].split("/")[0])

    def _close_dropdowns(self):
        for c in self.controls(("ComboBox",)):
            c.send_message(win32con.CB_SHOWDROPDOWN, 0, 0)

    def add_module(self):
        """Append a module row; returns its row index (1 = DAP, so the new row is the new slot count)."""
        before = self.slots_used()
        for attempt in range(3):          # a first press only closes an open in-place editor
            self.press("Add Module", settle=1.5)
            after = self.slots_used()
            if after == before + 1:
                return after
            log("  Add Module: slots still %d (attempt %d)" % (after, attempt + 1))
        raise SyconError("Add Module: slots %d -> %d" % (before, after))

    def module_combo(self, row):
        r = self.modules_page()
        for attempt in range(3):          # a first click may only close an editor left open on another cell
            mouse.click(coords=(r.left + MODULE_X, r.top + row_y(row)))
            time.sleep(1.5)
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
            time.sleep(1.5)
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
        r = self.modules_page()
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
        r = self.pane(MODULES_GRID_ID).rectangle()
        mouse.double_click(coords=(r.left + GLYPH_X, r.top + row_y(row)))
        time.sleep(1.2)
        self._close_dropdowns()

    def select_row(self, row):
        r = self.pane(MODULES_GRID_ID).rectangle()
        mouse.click(coords=(r.left + ICON_X, r.top + row_y(row)))
        time.sleep(0.8)
        self._close_dropdowns()

    # ---- submodules (an AL1202's ports) -------------------------------------------------------------------
    # Draft of 2026-10-23 evening, to be verified on the VM (scripts/probe_submodules.py): 'Add Submodule' with
    # the (expanded) module row selected appends a submodule row under its existing ones; the new row's Subslot
    # cell (x+60) is assumed to open ComboBox 1901 and its Submodule cell (x+150) ComboBox 1904 like a module
    # row's; rows beyond the grid's ~8 visible ones still need scrolling (open).
    def add_submodule(self, module_row):
        self.select_row(module_row)
        self.press("Add Submodule", settle=1.5)

    def set_subslot(self, row, subslot):
        self.set_slot(row, subslot)

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
            time.sleep(1.5)
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
        """Scroll the parameter grid by wheel notches; returns the measured pixel shift of its text."""
        before = self._dark_profile(r)
        mouse.scroll(coords=(r.left + r.width() // 2, r.top + r.height() // 2), wheel_dist=-notches)
        time.sleep(1.0)
        after = self._dark_profile(r)
        best, best_err = 0, None
        for s in range(0, r.height() - 20):
            err = sum(abs(before[y + s] - after[y]) for y in range(18, r.height() - s))
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
