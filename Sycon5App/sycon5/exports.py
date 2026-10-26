"""The controller's exports, as the user does them (recorded 2026-10-24 19:11 with `scripts/ui_recorder.py`, the
menu read with `scripts/probe_context_menu.py`): right-click the controller node > Additional Functions > Export >
`XML...` (the process data: `HilscherIO.xml`, the IO driver's input, beside the project) or `DBM/nxd...` (the
firmware configuration database: `nWid\\config.nxd`), a Win32 Save As dialog with the path typed, Save, the
`Confirm Save As` box answered Yes. SYCON.net reports `XML export of process data succeeded with device ...` /
`Export of DBM/nxd database succeeded with device ...` in its Output window; the file's existence and, for the
XML, its device list are the oracle here."""
from __future__ import annotations

import os
import re
import time
import xml.etree.ElementTree as ET

import win32gui
from pywinauto import Desktop

from .session import SyconError, log

EXPORT_KINDS = {"xml": "XML...", "nxd": "DBM/nxd...", "csv": "CSV..."}


def popup_menus():
    """[(hwnd, rect)] of the visible Win32 popup-menu windows (class #32768), the deepest first."""
    found = []

    def cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd) and win32gui.GetClassName(hwnd) == "#32768":
            found.append((hwnd, win32gui.GetWindowRect(hwnd)))
        return True
    win32gui.EnumWindows(cb, None)
    return found


def _click_menu_item(text, seen, timeout=6.0):
    """Click the menu item `text` in a popup menu not yet used (`seen` = handles used so far); returns the popup's
    handle. A hover opens no submenu in SYCON.net's menus - the item's own click does."""
    desk = Desktop(backend="uia")
    t0 = time.time()
    while time.time() - t0 < timeout:
        for hwnd, _rect in popup_menus():
            if hwnd in seen:
                continue
            try:
                items = Desktop(backend="uia").window(handle=hwnd).descendants(control_type="MenuItem")
            except Exception:  # noqa: BLE001
                continue
            for mi in items:
                if mi.window_text() == text:
                    mi.click_input()
                    time.sleep(1.2)
                    return hwnd
        time.sleep(0.5)
    raise SyconError("menu item %r not found (popups: %r)" % (text, [(h, r) for h, r in popup_menus()]))


def open_export_menu(session, item, kind):
    """Right-click the tree `item` (the controller node) and walk Additional Functions > Export > <kind>."""
    session.close_menus()
    session.bring_front()
    item.ensure_visible()
    item.click_input(button="right")
    time.sleep(1.2)
    seen = set()
    for text in ("Additional Functions", "Export", EXPORT_KINDS[kind]):
        seen.add(_click_menu_item(text, seen))
    log("  context menu: Additional Functions > Export > %s" % EXPORT_KINDS[kind])


def save_as(path, timeout=20.0):
    """Drive the Win32 'Save As' dialog: the full `path` into its File name field, Save, a 'Confirm Save As'
    answered Yes; waits for the dialog to close and for the file to be (re)written."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    before = os.path.getmtime(path) if os.path.exists(path) else 0
    desk = Desktop(backend="win32")
    dlg = desk.window(title="Save As", class_name="#32770")
    dlg.wait("visible", timeout=timeout)
    edit = dlg.child_window(control_id=1148, class_name="Edit")
    edit.set_edit_text(path)
    time.sleep(0.5)
    dlg.child_window(control_id=1, class_name="Button").click()        # Save
    time.sleep(1.0)
    confirm = desk.window(title="Confirm Save As")
    if confirm.exists(timeout=3):
        confirm.child_window(title_re="&?Yes").click()
        log("  Confirm Save As -> Yes")
    t0 = time.time()
    while time.time() - t0 < 60:
        if not dlg.exists() and os.path.exists(path) and os.path.getmtime(path) > before:
            log("  saved %s (%d bytes)" % (path, os.path.getsize(path)))
            return path
        time.sleep(1.0)
    raise SyconError("Save As: %s not written within 60 s" % path)


def export(session, item, kind, path):
    open_export_menu(session, item, kind)
    return save_as(path)


def process_data_devices(xml_path):
    """(controller display name, [device display names]) of a process-data export (`ProcessData/Controller/
    Channel/Device`), e.g. 'Cell Test[Anybus Communicator]<n0002-ct1-cc1-k63001>'."""
    root = ET.parse(xml_path).getroot()

    def local(tag):
        return tag.split("}")[-1]
    controller, devices = "", []
    for el in root.iter():
        if local(el.tag) == "Controller":
            controller = el.get("displayName", "")
        elif local(el.tag) == "Device":
            devices.append(el.get("displayName", ""))
    return controller, devices


NODE_SUFFIX = re.compile(r"\(#\d+\)\s*$")


def station_of(display_name):
    """The name of station inside a process-data display name: `label[type]<station>` - the controller's carries
    a node suffix after it, `CIFX_RE_PNM[CIFX RE/PNM]<n0001-...>(#1)` (2026-10-26)."""
    text = NODE_SUFFIX.sub("", display_name).strip()
    if "<" in text and text.endswith(">"):
        return text[text.rfind("<") + 1:-1]
    return display_name
