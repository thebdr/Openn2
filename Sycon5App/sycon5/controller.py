"""The controller (CIFX RE/PNM) dialog: the station names and IPs of the slaves are written HERE (a slave's own
General page is read-only), in the custom grids of the Device Table (name) and IP Address Table (IP), whose cells
open plain win32 editors on a click. The controller's own IP is on the Controller Network Settings page; change
it BEFORE the slave IPs (a slave IP outside the controller's subnet makes OK refuse with an Error that re-fires
at every dismissal).
"""
import time

from pywinauto import keyboard, mouse

from .dialog import ConfigDialog
from .session import SyconError, log

NETWORK_PAGE = "Controller Network Settings"
DEVICE_TABLE_PAGE, DEVICE_TABLE_ID = "Device Table", "210"
IP_TABLE_PAGE, IP_TABLE_ID = "IP Address Table", "212"
NET_IP_ID, NET_MASK_ID, NET_GATEWAY_ID = 213, 214, 215
ROW_Y0, ROW_H = 30, 18               # rows of the custom grids: row n centre at ROW_Y0 + ROW_H * (n - 1)
NAME_X, COMMIT_X, IP_X, IP_COMMIT_X = 200, 400, 260, 500
NAME_EDIT_ID = 1902


def _set_ip_control(ipc, ip):
    fields = sorted(ipc.children(), key=lambda c: c.rectangle().left)
    parts = ip.split(".")
    if len(fields) != 4 or len(parts) != 4:
        raise SyconError("not an IP control / IP: %r %r" % (len(fields), ip))
    for f, part in zip(fields, parts):
        f.set_edit_text(part)
    time.sleep(0.4)
    return ".".join(f.window_text() for f in sorted(ipc.children(), key=lambda c: c.rectangle().left))


class ControllerDialog(ConfigDialog):
    # ---- Controller Network Settings ----------------------------------------------------------------------
    def set_network(self, ip, mask=None, gateway=None):
        self.select_page(NETWORK_PAGE)
        for cid, value in ((NET_IP_ID, ip), (NET_MASK_ID, mask), (NET_GATEWAY_ID, gateway)):
            if value is None:
                continue
            ipc = [c for c in self.w32.descendants(class_name="SysIPAddress32") if c.control_id() == cid]
            if not ipc:
                raise SyconError("IP control %d not found" % cid)
            after = _set_ip_control(ipc[0], value)
            log("  network control %d -> %s" % (cid, after))
            if after != value:
                raise SyconError("IP control %d shows %s after writing %s" % (cid, after, value))
        warning = self.session.answer_box("Warning", "Yes")      # 'Changing subnet will automatically modify ...'
        if warning:
            log("  Warning answered Yes:", warning[:80])

    # ---- Device Table -------------------------------------------------------------------------------------
    def _grid(self, auto_id):
        return self.pane(auto_id).rectangle()

    def device_rows(self, max_rows=64):
        """[(row index, row y offset, name of station)] by clicking each row's name cell."""
        self.select_page(DEVICE_TABLE_PAGE)
        r = self._grid(DEVICE_TABLE_ID)
        rows = []
        for n in range(1, max_rows + 1):
            y = ROW_Y0 + ROW_H * (n - 1)
            if r.top + y > r.bottom - 5:
                break
            mouse.click(coords=(r.left + NAME_X, r.top + y))
            time.sleep(0.8)
            eds = self.controls(("Edit",), cid=NAME_EDIT_ID)
            if not eds:
                break
            rows.append((n, y, eds[0].window_text()))
        mouse.click(coords=(r.left + COMMIT_X, r.top + ROW_Y0))
        time.sleep(0.5)
        return rows

    def find_row(self, station):
        for n, y, name in self.device_rows():
            if name == station:
                return n, y
        raise SyconError("station %r not in the Device Table" % station)

    def set_station_name(self, row_y, name):
        self.select_page(DEVICE_TABLE_PAGE)
        r = self._grid(DEVICE_TABLE_ID)
        mouse.click(coords=(r.left + NAME_X, r.top + row_y))
        time.sleep(0.9)
        ed = self.controls(("Edit",), cid=NAME_EDIT_ID)
        if not ed:
            raise SyconError("no name editor on row y+%d" % row_y)
        if ed[0].window_text() != name:
            ed[0].select()
            time.sleep(0.2)
            keyboard.send_keys(name, with_spaces=True)
            time.sleep(0.4)
        mouse.click(coords=(r.left + COMMIT_X, r.top + row_y))      # commit: a read-only cell
        time.sleep(0.9)
        mouse.click(coords=(r.left + NAME_X, r.top + row_y))        # verify
        time.sleep(0.9)
        value = self.controls(("Edit",), cid=NAME_EDIT_ID)[0].window_text()
        mouse.click(coords=(r.left + COMMIT_X, r.top + row_y))
        time.sleep(0.6)
        log("  Device Table row y+%d: name -> %r" % (row_y, value))
        if value != name:
            raise SyconError("name of station reads %r after writing %r" % (value, name))

    # ---- IP Address Table ---------------------------------------------------------------------------------
    def set_station_ip(self, row_y, ip):
        self.select_page(IP_TABLE_PAGE)
        r = self._grid(IP_TABLE_ID)
        mouse.click(coords=(r.left + IP_X, r.top + row_y))
        time.sleep(0.9)
        ipc = self.controls(("SysIPAddress32",))
        if not ipc:
            raise SyconError("no IP editor on row y+%d" % row_y)
        before = ".".join(f.window_text() for f in sorted(ipc[0].children(), key=lambda c: c.rectangle().left))
        _set_ip_control(ipc[0], ip)
        mouse.click(coords=(r.left + IP_COMMIT_X, r.top + row_y))   # commit
        time.sleep(0.9)
        mouse.click(coords=(r.left + IP_X, r.top + row_y))          # verify
        time.sleep(0.9)
        ipc = self.controls(("SysIPAddress32",))
        after = ".".join(f.window_text() for f in sorted(ipc[0].children(), key=lambda c: c.rectangle().left))
        mouse.click(coords=(r.left + IP_COMMIT_X, r.top + row_y))
        time.sleep(0.6)
        log("  IP Address Table row y+%d: %s -> %s" % (row_y, before, after))
        if after != ip:
            raise SyconError("IP reads %s after writing %s" % (after, ip))
