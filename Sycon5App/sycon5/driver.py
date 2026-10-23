"""SyconDriver - the operations of Sycon5App on a running SYCON.net, each a proven GUI mechanism verified by
the netProject tree and, in the end, by `read_project` on the saved file.

Nothing is saved unless the caller calls save() / save_as() (the OP5 rule: the user saves after review).
"""
import os
import time

from pywinauto import keyboard

from . import catalog
from .controller import ControllerDialog
from .device import DeviceDialog
from .readback import read_project
from .session import Session, SyconError, log

DriverError = SyconError


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
        self.session.launch(project).login()
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
        raise SyconError("the project was not saved (%s unchanged)" % xml_path)

    @staticmethod
    def read_back(xml_or_spj):
        return read_project(xml_or_spj)

    # ---- stations --------------------------------------------------------------------------------------------
    def add_controller(self, item="CIFX RE/PNM"):
        node = catalog.add_device(self.session, "master", item)
        log("controller added:", node)
        return node

    def add_station(self, item, kind="slave"):
        node = catalog.add_device(self.session, kind, item)
        self.model.setdefault(node["station"], {"slots": {}})
        log("station added:", node)
        return node

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
        if not any("<%s>" % name in node for node in nodes):
            raise SyconError("the netProject tree does not show <%s>: %r" % (name, nodes))
        if station in self.model:
            self.model[name] = self.model.pop(station)
        log("station %s -> %s @ %s" % (station, name, ip))

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
        """values: {parameter index within the submodule's record (0 = first): value text}. The module's row in
        the Modules grid is 1 + its position among the plugged slots (this driver's model); its first submodule
        row is the one below it once expanded."""
        slots = sorted(self.model.get(station, {"slots": {}})["slots"])
        if slot not in slots:
            raise SyconError("slot %d of %s unknown to this driver (plug it first): %r" % (slot, station, slots))
        row = 2 + slots.index(slot)
        dlg = DeviceDialog(self.session, station)
        try:
            dlg.modules_page()
            dlg.expand_row(row)
            dlg.select_row(row + 1)
            dlg.dataset("Parameter")
            dlg.set_parameters(values)
            errs = dlg.apply()
            if errs:
                raise SyconError("Apply refused: %r" % errs)
            dlg.close(keep=True)
        except SyconError:
            if dlg.is_open():
                dlg.close(keep=False)
            raise
        log("parameters set on %s slot %d: %r" % (station, slot, values))
