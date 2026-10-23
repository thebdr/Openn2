"""A DTM configuration dialog (`netProject - Configuration <label>`): opened from the netProject tree's context
menu, pages selected through the UIA SelectionItem pattern, buttons pressed by win32 BM_CLICK (never by mouse),
in-place grid editors reached as win32 children with control ids >= 1900.

Closing: the controller dialog's OK closes it; a slave dialog's OK never does - use Apply then Cancel; a
Cancel after unapplied changes asks 'Configuration data has been changed. Do you want to save the data?'
(Yes keeps the data, No discards it).
"""
import ctypes
import time

from pywinauto import Desktop

from .session import Session, SyconError, log

BUTTON_IDS = {"OK": 1, "Cancel": 2, "Apply": 2204, "Help": 9, "Add Module": 307, "Add Submodule": 308, "Remove": 309}
QUESTION = "Question"


class ConfigDialog:
    def __init__(self, session: Session, station: str, timeout=300.0):
        self.session = session
        self.station = station
        already = session.dialogs()
        mine = [d for d in already if "<%s>" % station.lower() in d.window_text().lower()]
        if mine:
            self.uia = mine[0]
        elif already:
            raise SyconError("another dialog is open: %r" % [d.window_text()[:40] for d in already])
        else:
            self.uia = self._open(timeout)
        self.w32 = Desktop(backend="win32").window(handle=self.uia.handle)
        log("dialog:", self.uia.window_text())
        self.maximize()

    def maximize(self):
        """Maximize the dialog (user 2026-10-23: "maximize the configuration windows ... some systems may have
        100+ nodes"): the grids show many rows at once. Their columns scale with the width, so every column
        offset measured on the control maps is scaled by the grid's width (`DeviceDialog.sx`, `ControllerDialog.cx`)."""
        user32 = ctypes.windll.user32
        if not user32.IsZoomed(self.uia.handle):
            user32.ShowWindow(self.uia.handle, 3)          # SW_MAXIMIZE
            time.sleep(1.2)
        d = self.uia.rectangle()
        log("  dialog %s: %dx%d" % ("maximized" if user32.IsZoomed(self.uia.handle) else "NOT maximized", d.width(), d.height()))

    def _open(self, timeout):
        s = self.session
        s.close_menus()
        s.bring_front()
        item = s.station_item(self.station)
        s.safe_click(item, button="right")
        menu = s.wait_menu(15)
        if menu is None:
            raise SyconError("no context menu for <%s>" % self.station)
        entry = [c for c in menu.children() if c.window_text().startswith("Configuration")]
        if not entry:
            s.close_menus()
            raise SyconError("no 'Configuration...' entry in the context menu")
        s.safe_click(entry[0], allow_menu=True)
        t0 = time.time()
        while time.time() - t0 < timeout:
            time.sleep(1.5)
            errs = s.dismiss_errors()
            if errs:
                raise SyconError("errors while opening the dialog of <%s>: %r" % (self.station, errs))
            for d in s.dialogs():
                if "<%s>" % self.station.lower() in d.window_text().lower():
                    time.sleep(3.0)
                    return d
            s.ensure_alive("opening the dialog of <%s>" % self.station)
        raise SyconError("the dialog of <%s> did not open" % self.station)

    # ---- structure ----------------------------------------------------------------------------------------
    def is_open(self):
        return any(w.handle == self.uia.handle for w in self.session.top_windows())

    def rect(self):
        return self.uia.rectangle()

    def pane(self, auto_id):
        panes = [p for p in self.uia.descendants(control_type="Pane") if p.element_info.automation_id == auto_id]
        if not panes:
            raise SyconError("pane %s not found in the dialog" % auto_id)
        return panes[0]

    def fit(self, pane_auto_id, ref_w, ref_h):
        """Resize the dialog so that a pane (a custom grid) has its reference size: the grids' columns scale with
        the dialog, every measured offset holds at the size of the control maps only, and SYCON.net reopens a
        dialog at the size the user left it (2026-10-23 18:27: the Modules grid 187 px wider after a manual
        check, the Module cell click landing in another column). Returns True when resized."""
        resized = False
        for _ in range(3):                # the pane's height follows the dialog's only in part: a few steps
            r = self.pane(pane_auto_id).rectangle()
            dw, dh = r.width() - ref_w, r.height() - ref_h
            if abs(dw) < 4 and abs(dh) < 4:
                break
            d = self.uia.rectangle()
            ctypes.windll.user32.MoveWindow(self.uia.handle, d.left, d.top, d.width() - dw, d.height() - dh, True)
            time.sleep(1.0)
            resized = True
            r2 = self.pane(pane_auto_id).rectangle()
            log("  dialog resized by (%d, %d): pane %s now %dx%d" % (-dw, -dh, pane_auto_id, r2.width(), r2.height()))
        r = self.pane(pane_auto_id).rectangle()
        if abs(r.width() - ref_w) >= 4:   # the columns scale with the width: that one must hold; the height only
            raise SyconError("pane %s is %dx%d after the resize (reference %dx%d)" % (     # changes the rows shown
                pane_auto_id, r.width(), r.height(), ref_w, ref_h))
        return resized

    def panes_of_class(self, class_prefix):
        return [p for p in self.uia.descendants(control_type="Pane") if p.class_name().startswith(class_prefix)]

    def select_page(self, name):
        self.session.dismiss_errors()
        nav = self.uia.descendants(control_type="Tree")[0]
        items = [i for i in Session._iter_items(nav) if i.window_text() == name]
        if not items:
            raise SyconError("page %r not in the navigation tree" % name)
        items[0].select()
        time.sleep(1.5)

    def texts(self, prefix):
        return [t.window_text() for t in self.uia.descendants(control_type="Text") if t.window_text().startswith(prefix)]

    # ---- win32 controls -------------------------------------------------------------------------------------
    def controls(self, classes=("Edit", "ComboBox", "SysIPAddress32"), min_id=1900, cid=None):
        out = []
        for c in self.w32.descendants():
            try:
                if c.is_visible() and c.class_name() in classes and c.control_id() >= min_id and (cid is None or c.control_id() == cid):
                    out.append(c)
            except Exception:  # noqa: BLE001
                pass
        return out

    def combo(self, cid):
        """The VISIBLE ComboBox with this control id: every page of a dialog is instantiated at once and the ids
        repeat across pages (220 is the Stations Timing page's 'Name of station' AND a port-speed combo of
        another page - 2026-10-23 18:22)."""
        c = [c for c in self.w32.descendants(class_name="ComboBox") if c.control_id() == cid and c.is_visible()]
        return c[0] if c else None

    def button(self, name):
        b = [b for b in self.w32.descendants(class_name="Button") if b.control_id() == BUTTON_IDS[name] and b.is_visible()]
        if not b:
            raise SyconError("button %r not found" % name)
        return b[0]

    def press(self, name, settle=2.0):
        self.button(name).click()
        time.sleep(settle)

    # ---- closing ------------------------------------------------------------------------------------------
    def _wait_closed(self, what, keep, timeout=60.0):
        s = self.session
        t0 = time.time()
        while time.time() - t0 < timeout:
            if not self.is_open():
                log("dialog closed after", what)
                time.sleep(3.0)
                s.ensure_alive("closing the dialog with " + what)
                return
            if s.boxes(QUESTION):
                text = s.answer_box(QUESTION, "Yes" if keep else "No")
                log("Question:", text, "->", "Yes" if keep else "No")
            if s.boxes("Warning"):                       # e.g. 'Changing subnet will automatically modify ...'
                text = s.answer_box("Warning", "Yes" if keep else "No")
                log("Warning:", text, "->", "Yes" if keep else "No")
            errs = s.dismiss_errors()
            if errs:
                raise SyconError("Error after %s: %r" % (what, errs))
            time.sleep(1.0)
        raise SyconError("dialog still open %d s after %s" % (timeout, what))

    def apply(self):
        """Apply = commit the dialog's data to the project; returns the Error texts (empty when fine)."""
        self.press("Apply")
        errs = self.session.dismiss_errors()
        if errs:
            log("errors after Apply:", errs)
        return errs

    def close(self, keep=True):
        """Cancel the dialog; answer the 'save the data?' question with Yes (keep) or No (discard)."""
        self.session.dismiss_errors()
        self.press("Cancel")
        self._wait_closed("Cancel", keep)

    def ok(self):
        """OK (closes the controller dialog). An Error after OK (e.g. 'not in the same subnet') is raised
        after backing out of the dialog with Cancel / No so the session stays usable."""
        self.press("OK")
        errs = self.session.dismiss_errors()
        if errs:
            try:
                if self.is_open():
                    self.press("Cancel")
                    self._wait_closed("Cancel after an OK error", keep=False)
            finally:
                pass
            raise SyconError("OK refused: %r" % errs)
        self._wait_closed("OK", keep=True)
