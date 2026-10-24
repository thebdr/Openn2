"""SyconDriver - the operations of Sycon5App on a running SYCON.net, each a proven GUI mechanism verified by
the netProject tree and, in the end, by `read_project` on the saved file.

Nothing is saved unless the caller calls save() / save_as() (the OP5 rule: the user saves after review).
"""
import os
import re
import time

from pywinauto import keyboard

from . import catalog
from .controller import ControllerDialog
from .device import DeviceDialog
from .readback import read_project
from .session import Session, SyconError, log

DriverError = SyconError
CONTEXT_COPY, CONTEXT_PASTE = 34503, 34504      # the netProject context menu's Copy / Paste command ids


class SyconDriver:
    def __init__(self):
        self.session = Session()
        self.model = {}            # station name -> {"slots": {slot: module}} as this driver plugged them

    # ---- session --------------------------------------------------------------------------------------------
    def open(self, project=None):
        """Launch SYCON.net (on a project when given) and log in; attach when it already runs."""
        if self.session.attach_if_running():
            log("attached to the running SYCON.net:", self.session.title())
            return self
        # a saved project loads one DTM per station: 40-60 stations took longer than a minute (02:00, "the main
        # window did not appear") - the main window is awaited for up to 15 minutes
        self.session.launch(project).login(timeout=900.0)
        log("opened:", self.session.title())
        return self

    def close(self):
        return self.session.close()

    def is_alive(self):
        return self.session.is_alive()

    def stations(self):
        return [catalog.parse_node(n) for n in self.session.nodes() if catalog.parse_node(n)]

    # ---- project ---------------------------------------------------------------------------------------------
    def new_project(self, timeout=30.0):
        """File > New (WM_COMMAND); a prompt to save the current project is answered No."""
        self.session.post_command("new")
        time.sleep(3.0)
        for title in ("SYCON.net", "Question"):
            self.session.answer_box(title, "No", timeout=2.0)
        t0 = time.time()
        while time.time() - t0 < timeout:
            if "Untitled" in self.session.title():
                log("new project:", self.session.title(), self.session.nodes())
                self.model = {}
                return
            time.sleep(1.0)
        raise SyconError("no new project (title %r)" % self.session.title())

    def save_as(self, spj_path, timeout=40.0):
        """File > Save as... through the common file dialog (file name box = Edit 1148). Returns the XML path."""
        s = self.session
        s.bring_front()
        before = {w.handle for w in s.top_windows()}
        s.post_command("save_as")
        fd = None
        t0 = time.time()
        while time.time() - t0 < 20 and fd is None:
            time.sleep(1.0)
            for w in s.top_windows():
                if w.handle not in before and w.class_name() == "#32770" and w.descendants(control_type="Edit"):
                    fd = w
        if fd is None:
            raise SyconError("the Save As dialog did not appear")
        edits = [e for e in fd.descendants(control_type="Edit")
                 if e.element_info.automation_id in ("1148", "1001") or e.window_text().startswith(("File name", "Nome file"))]
        if not edits:
            raise SyconError("file name box not found in the Save As dialog")
        edits[0].set_focus()
        time.sleep(0.3)
        edits[0].set_edit_text(spj_path)
        time.sleep(0.5)
        keyboard.send_keys("{ENTER}")
        xml = spj_path[:-4] + "\\_S129\\SYCON_net.xml"
        t0 = time.time()
        while time.time() - t0 < timeout:
            time.sleep(1.0)
            s.answer_box("Confirm Save As", "Yes", timeout=0.2)
            if os.path.exists(xml):
                time.sleep(3.0)
                break
        else:
            raise SyconError("the project was not saved to %s" % spj_path)
        errs = s.dismiss_errors()
        log("saved as:", spj_path, "| title:", s.title(), "| errors:", errs)
        return xml

    def save(self, xml_path, timeout=30.0):
        """File > Save of a named project; waits for its XML to be rewritten."""
        mtime0 = os.path.getmtime(xml_path) if os.path.exists(xml_path) else 0
        self.session.bring_front()
        self.session.post_command("save")
        t0 = time.time()
        while time.time() - t0 < timeout:
            time.sleep(1.0)
            if os.path.exists(xml_path) and os.path.getmtime(xml_path) > mtime0:
                time.sleep(2.0)
                log("saved:", xml_path)
                return xml_path
        log("save: %s unchanged after %d s (nothing to save?) - going on" % (xml_path, timeout))
        return xml_path

    @staticmethod
    def read_back(xml_or_spj):
        return read_project(xml_or_spj)

    # ---- stations --------------------------------------------------------------------------------------------
    def add_controller(self, item="CIFX RE/PNM", gsdml=None):
        node = catalog.add_device(self.session, "master", item, gsdml or None)
        log("controller added:", node)
        return node

    def add_station(self, item, kind="slave", gsdml=None):
        """Add a station from the catalog; `gsdml` names the file its catalog entry must come from (the catalog
        lists one same-named entry per GSDML version)."""
        node = catalog.add_device(self.session, kind, item, gsdml or None)
        self.model.setdefault(node["station"], {"slots": {}})
        log("station added:", node)
        return node

    def clone_station(self, source, count=1):
        """Copy the source node in the netProject tree and paste it `count` times - SYCON.net names a clone
        `<source>-001`, `-002`, ... and gives it the next free IP (the AutoHotkey way: click, Ctrl+C, click,
        Ctrl+V - verified 2026-10-23; the context menu's Copy / Paste command ids posted to the main window
        produce nothing and stay as the fallback). Returns the new nodes."""
        s = self.session
        s.close_menus()
        s.bring_front()
        source_type = catalog.parse_node(s.station_item(source).window_text())["type"]
        new_nodes = []
        for _ in range(count):
            before = s.nodes()
            node = None
            for way in ("keys", "command"):
                item = self._select_station(source)
                if way == "command":
                    s.post_command_id(CONTEXT_COPY, "Copy")
                else:
                    keyboard.send_keys("^c")
                time.sleep(0.8)
                item = self._select_station(source)
                if way == "command":
                    s.post_command_id(CONTEXT_PASTE, "Paste")
                else:
                    keyboard.send_keys("^v")
                t0 = time.time()
                while time.time() - t0 < (10 if way == "command" else 30):
                    time.sleep(1.0)
                    errs = s.dismiss_errors()
                    s.ensure_alive("the paste of %s" % source)
                    if errs:
                        raise SyconError("errors after pasting %s: %r" % (source, errs))
                    new = [n for n in s.nodes() if n not in before]
                    if new:
                        node = catalog.parse_node(new[0])
                        break
                if node:
                    break
                log("  paste by %s produced no node" % way)
            if node is None:
                raise SyconError("no node appeared after pasting %s" % source)
            if node["type"] != source_type or len(new) != 1:
                # 21:26: after a catalog drop the tree had lost the focus, Ctrl+C copied nothing and Ctrl+V pasted
                # the clipboard's earlier node - a station of the wrong type that the build then mis-named
                raise SyconError("pasting %s (%s) produced %r - the clipboard held another node" % (source, source_type, new))
            self.model.setdefault(node["station"], {"slots": {}})
            new_nodes.append(node)
            log("cloned %s -> %s" % (source, node["station"]))
        return new_nodes

    def _select_station(self, station, attempts=3):
        """Click the station's node in the netProject tree until the tree reports it selected (the first click
        after a catalog drag-drop only moves the focus back from the catalog, 2026-10-23 21:26)."""
        s = self.session
        for attempt in range(attempts):
            item = s.station_item(station)
            s.safe_click(item)
            time.sleep(0.4)
            try:
                if item.is_selected():
                    return item
            except Exception:  # noqa: BLE001
                return item
            log("  node <%s> not selected after click %d" % (station, attempt + 1))
        raise SyconError("the node <%s> does not get selected" % station)

    def controller_station(self):
        for n in self.stations():
            if n["suffix"].startswith("(#") or "PNM" in n["type"]:
                return n["station"]
        raise SyconError("no controller in the project")

    def set_controller_network(self, ip, mask=None, gateway=None):
        dlg = ControllerDialog(self.session, self.controller_station())
        try:
            dlg.set_network(ip, mask, gateway)
            dlg.ok()
        except SyconError:
            if dlg.is_open():
                dlg.close(keep=False)
            raise

    def set_station_name_ip(self, station, name, ip):
        """Rename a slave (its PROFINET name of station) and set its IP in the controller's grids; the tree
        must show the new name afterwards."""
        dlg = ControllerDialog(self.session, self.controller_station())
        try:
            n, y = dlg.find_row(station)
            dlg.set_station_name(y, name)
            dlg.set_station_ip(y, ip)
            dlg.ok()
        except SyconError:
            if dlg.is_open():
                dlg.close(keep=False)
            raise
        nodes = self.session.nodes()
        if not any("<%s>" % name.lower() in node.lower() for node in nodes):
            raise SyconError("the netProject tree does not show <%s>: %r" % (name, nodes))
        if station in self.model:
            self.model[name] = self.model.pop(station)
        log("station %s -> %s @ %s" % (station, name, ip))

    def rename_stations(self, mapping, current_ips=None):
        """mapping: {current station name: (new name, ip)} - one controller dialog pass for all of them;
        `current_ips` = {current name: the IP it has now} as far as known (the row identity check)."""
        dlg = ControllerDialog(self.session, self.controller_station())
        try:
            missing = dlg.rename_and_address(mapping, current_ips)
            dlg.ok()
        except SyconError:
            if dlg.is_open():
                # the names pass is all-or-nothing (Cancel, the data discarded); a failure in the IP pass keeps the
                # names and the IPs written so far (Cancel, the data kept) - a resume re-addresses the stations
                # whose saved IP differs from the table (2026-10-24: a 60-station pass lost to one slow editor)
                dlg.close(keep=getattr(dlg, "phase", "") == "ips")
            raise
        if missing:
            raise SyconError("stations not found in the Device Table: %r" % missing)
        nodes = self.session.nodes()
        absent = [new for new, _ip in mapping.values() if not any("<%s>" % new.lower() in n.lower() for n in nodes)]
        if absent:
            raise SyconError("the netProject tree does not show %r" % absent)
        for old, (new, _ip) in mapping.items():
            self.model[new] = self.model.pop(old, {"slots": {}})
        log("renamed and addressed %d stations" % len(mapping))

    def set_stations_timing(self, timing):
        """timing: {station: updating time in ms} - one pass of the controller's Stations Timing page."""
        dlg = ControllerDialog(self.session, self.controller_station())
        try:
            shown = dlg.set_stations_timing(timing)
            dlg.ok()
        except SyconError:
            if dlg.is_open():
                dlg.close(keep=False)
            raise
        log("stations timing set: %r" % shown)
        return shown

    def plug_modules(self, station, specs):
        """Append modules in order in ONE dialog; a spec is a combo text or 'order:<order number>'. Returns the
        texts chosen."""
        dlg = DeviceDialog(self.session, station)
        chosen = []
        try:
            dlg.modules_page()
            for spec in specs:
                row = dlg.add_module()
                text = dlg.resolve_module(row, spec)
                dlg.set_module(row, text)
                chosen.append(text)
            errs = dlg.apply()
            for _round in range(2):
                # 'Slot [1] contains a module without submoduls': select THAT module's row and Add Submodule
                # (pressed with another row current it answers 'No possible submodule found', 2026-10-23 17:21)
                without = sorted({int(n) for e in errs if "without submodul" in e for n in re.findall(r"Slot \[(\d+)\]", e)})
                if not without:
                    break
                for n in without:
                    log("  slot %d without submodule -> its row selected, Add Submodule" % n)
                    dlg.select_row(1 + n)
                    dlg.press("Add Submodule", settle=1.5)
                    more = self.session.dismiss_errors()
                    if more:
                        raise SyconError("Add Submodule on slot %d refused: %r" % (n, more))
                errs = dlg.apply()
            if errs:
                raise SyconError("Apply refused: %r" % errs)
            dlg.close(keep=True)
        except SyconError:
            if dlg.is_open():
                dlg.close(keep=False)
            raise
        used = self.model.setdefault(station, {"slots": {}})["slots"]
        for text in chosen:
            used[max(used) + 1 if used else 1] = text
        log("modules plugged on %s: %r" % (station, chosen))
        return chosen

    def plug_submodules(self, station, slot, wanted, first_subslot=2):
        """wanted: [(subslot, submodule text)] in subslot order, appended under the module in `slot` (an AL1202's
        `8 Ports` in slot 1 holds the IO-Link Master in sub 1; SYCON.net numbers every added submodule itself,
        from `first_subslot` on, so the wanted subslots must be exactly that sequence). Each 'Add Submodule'
        appends a row at the end of the grid; its submodule is chosen through the in-place combo."""
        expected = list(range(first_subslot, first_subslot + len(wanted)))
        if [sub for sub, _t in wanted] != expected:
            raise SyconError("subslots %r wanted on %s slot %d, SYCON.net assigns %r" % (
                [sub for sub, _t in wanted], station, slot, expected))
        dlg = DeviceDialog(self.session, station)
        chosen = []
        try:
            dlg.modules_page()
            row = 1 + slot                      # the DAP is row 1, the slots contiguous from 1
            dlg.collapse_all()
            dlg.ensure_expanded(row)
            for _subslot, text in wanted:
                sub_row = dlg.add_submodule(row)
                chosen.append(dlg.set_submodule(sub_row, text))
            errs = dlg.apply()
            if errs:
                raise SyconError("Apply refused: %r" % errs)
            dlg.close(keep=True)
        except SyconError:
            if dlg.is_open():
                dlg.close(keep=False)
            raise
        subs = self.model.setdefault(station, {"slots": {}}).setdefault("submodules", {})
        for (subslot, _text), text in zip(wanted, chosen):
            subs[(slot, subslot)] = text
        log("submodules plugged on %s slot %d: %r" % (station, slot, chosen))
        return chosen

    def set_dap_submodules(self, station, wanted):
        """wanted: [(subslot, submodule text)] for the pluggable port submodules of the device itself (a SCALANCE
        XC216-4C's combo ports 32769-32772: `SFP 991-1 A` / `RJ45 1 GBit`). The DAP (row 1) expanded shows its
        submodule rows in subslot order - 1 (the device), 32768 (PN-IO), 32769.. (the ports) - so port n sits
        on row 3 + n; each one's submodule is chosen through the in-place combo like a module's. Draft of
        2026-10-23 20:30, to be verified by scripts/probe_switch.py."""
        dlg = DeviceDialog(self.session, station)
        chosen = []
        try:
            dlg.modules_page()
            dlg.collapse_all()
            dlg.ensure_expanded(1)
            for subslot, text in wanted:
                row = 3 + (subslot - 0x8000)
                chosen.append(dlg.set_submodule(row, text))
            errs = dlg.apply()
            if errs:
                raise SyconError("Apply refused: %r" % errs)
            dlg.close(keep=True)
        except SyconError:
            if dlg.is_open():
                dlg.close(keep=False)
            raise
        log("port submodules set on %s: %r" % (station, chosen))
        return chosen

    # ---- modules and parameters -------------------------------------------------------------------------------
    def plug_module(self, station, module, slot=None):
        """Append a module to the slave (next free slot, or `slot` through the Slot combo) and choose it."""
        dlg = DeviceDialog(self.session, station)
        try:
            dlg.modules_page()
            row = dlg.add_module()
            dlg.set_module(row, module)
            if slot is not None:
                dlg.set_slot(row, slot)
            errs = dlg.apply()
            if errs and any("without submodul" in e for e in errs):
                log("  module without submodule -> Add Submodule, Apply again")
                dlg.select_row(row)
                dlg.press("Add Submodule", settle=1.5)
                errs = self.session.dismiss_errors() + dlg.apply()
            if errs:
                raise SyconError("Apply refused: %r" % errs)
            dlg.close(keep=True)
        except SyconError:
            if dlg.is_open():
                dlg.close(keep=False)
            raise
        used = self.model.setdefault(station, {"slots": {}})["slots"]
        used[slot if slot is not None else (max(used) + 1 if used else 1)] = module
        log("module plugged on %s: %r (row %d)" % (station, module, row))
        return row

    def set_parameters(self, station, slot, values):
        """values: {parameter index within the submodule's first record (0 = first): value text}."""
        return self.set_module_parameters(station, slot, [(str(k), v) for k, v in sorted(values.items())])

    def set_module_parameters(self, station, slot, params, subslot=1):
        """params: [(name, value)] - a numeric name is the parameter's index within the module's first record,
        `potential_group` the module's last parameter row (an ET200SP's `Potential group`); `record:<index>` entries
        are verification-only and skipped here. ONE dialog: the module row is 1 + its slot (the slots are
        contiguous from 1 in the projects this driver builds - no model needed, so a resumed build can set them
        too); its submodule rows follow it once expanded - the first one for `subslot` 1, the DAP's interface
        submodule 32768 (a switch's PN-IO) second; the Dataset `Parameter` shows the grid."""
        row = 1 + slot
        params = [(n, v) for n, v in params if not str(n).startswith("record:")]
        by_index = {int(n): v for n, v in params if str(n).isdigit()}
        others = [(n, v) for n, v in params if not str(n).isdigit()]
        unknown = [n for n, _v in others if n != "potential_group"]
        if unknown:
            raise SyconError("unknown parameter names %r for %s slot %d" % (unknown, station, slot))
        if not by_index and not others:
            return
        sub_offset = 1 if subslot == 1 else (2 + subslot - 0x8000 if subslot >= 0x8000 else subslot)
        dlg = DeviceDialog(self.session, station)
        try:
            dlg.modules_page()
            dlg.collapse_all()
            dlg.ensure_expanded(row)
            dlg.select_row(row + sub_offset)
            dlg.dataset("Parameter")
            if by_index:
                dlg.set_parameters(by_index)
            for name, value in others:
                dlg.set_last_param(value)
            errs = dlg.apply()
            if errs:
                raise SyconError("Apply refused: %r" % errs)
            dlg.close(keep=True)
        except SyconError:
            if dlg.is_open():
                dlg.close(keep=False)
            raise
        log("parameters set on %s slot %d: %r" % (station, slot, params))
