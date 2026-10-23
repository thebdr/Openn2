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
TIMING_PAGE = "Stations Timing"
TIMING_NAME_COMBO_ID, TIMING_UPDATE_COMBO_ID, TIMING_WATCHDOG_EDIT_ID = 220, 223, 224
ROW_Y0, ROW_H = 27, 16               # the custom grids: an 18 px header, 16 px rows - row n (0-based) centre at ROW_Y0 + ROW_H * n (measured 2026-10-23)
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

    # ---- Stations Timing ----------------------------------------------------------------------------------
    def set_stations_timing(self, timing):
        """timing: {name of station: updating time in ms}. The Stations Timing page: each station picked in the
        'Name of station' combo (220), its updating time chosen in the combo (223) - the watchdog (Edit 224)
        follows, 3x (user 2026-10-23: 8 ms for every node). Returns {station: (updating, watchdog)} as shown."""
        self.select_page(TIMING_PAGE)
        names = self.combo(TIMING_NAME_COMBO_ID)
        if names is None:
            raise SyconError("the 'Name of station' combo (%d) not found on the Stations Timing page" % TIMING_NAME_COMBO_ID)
        listed = names.item_texts()
        by_lower = {n.lower(): n for n in listed}
        missing = [st for st in timing if st.lower() not in by_lower]
        if missing:
            raise SyconError("stations not listed on the Stations Timing page: %r (listed %r)" % (missing, listed))
        shown = {}
        for st, ms in timing.items():
            self.combo(TIMING_NAME_COMBO_ID).select(by_lower[st.lower()])
            time.sleep(0.8)
            upd = self.combo(TIMING_UPDATE_COMBO_ID)
            want = str(int(ms)) if float(ms).is_integer() else str(ms)
            if upd.selected_text() != want:
                try:
                    upd.select(want)
                except (IndexError, ValueError) as ex:
                    raise SyconError("updating time %r not offered for %s: %r (%s)" % (want, st, upd.item_texts(), ex))
                time.sleep(0.8)
            wd = [c for c in self.w32.descendants(class_name="Edit") if c.control_id() == TIMING_WATCHDOG_EDIT_ID and c.is_visible()]
            shown[st] = (self.combo(TIMING_UPDATE_COMBO_ID).selected_text(), wd[0].window_text() if wd else "")
            log("  timing %s: %s ms (watchdog %s ms)" % (st, shown[st][0], shown[st][1]))
            if shown[st][0] != want:
                raise SyconError("updating time of %s reads %r after choosing %r" % (st, shown[st][0], want))
        return shown

    # ---- Device Table -------------------------------------------------------------------------------------
    GRID_REF_W = 661                   # the Device Table / IP Address Table grids' width at the dialog's default size
    _grid_rect = None

    def _grid(self, auto_id):
        self._grid_rect = self.pane(auto_id).rectangle()
        return self._grid_rect

    def cx(self, x):
        """A grid column offset measured at the reference width, scaled to the grid as shown (maximized)."""
        r = self._grid_rect or self._grid(DEVICE_TABLE_ID)
        return int(round(x * r.width() / self.GRID_REF_W))

    def device_rows(self, max_rows=64):
        """[(row index, row y offset, name of station)] by clicking each row's name cell."""
        self.select_page(DEVICE_TABLE_PAGE)
        r = self._grid(DEVICE_TABLE_ID)
        rows = []
        for n in range(1, max_rows + 1):
            y = ROW_Y0 + ROW_H * (n - 1)
            if r.top + y > r.bottom - 8:
                break
            mouse.click(coords=(r.left + self.cx(NAME_X), r.top + y))
            time.sleep(0.8)
            eds = self.controls(("Edit",), cid=NAME_EDIT_ID)
            if not eds:
                break
            rows.append((n, y, eds[0].window_text()))
        mouse.click(coords=(r.left + self.cx(COMMIT_X), r.top + ROW_Y0))
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
        mouse.click(coords=(r.left + self.cx(NAME_X), r.top + row_y))
        time.sleep(0.9)
        ed = self.controls(("Edit",), cid=NAME_EDIT_ID)
        if not ed:
            raise SyconError("no name editor on row y+%d" % row_y)
        if ed[0].window_text() != name:
            ed[0].select()
            time.sleep(0.2)
            keyboard.send_keys(name, with_spaces=True)
            time.sleep(0.4)
        mouse.click(coords=(r.left + self.cx(COMMIT_X), r.top + row_y))      # commit: a read-only cell
        time.sleep(0.9)
        mouse.click(coords=(r.left + self.cx(NAME_X), r.top + row_y))        # verify
        time.sleep(0.9)
        value = self.controls(("Edit",), cid=NAME_EDIT_ID)[0].window_text()
        mouse.click(coords=(r.left + self.cx(COMMIT_X), r.top + row_y))
        time.sleep(0.6)
        log("  Device Table row y+%d: name -> %r" % (row_y, value))
        if value.lower() != name.lower():
            raise SyconError("name of station reads %r after writing %r" % (value, name))

    # ---- many stations: the grids scrolled by wheel, the shift measured from the pixels ------------------
    def _scroll(self, r, notches):
        from .drawing import dark_profile, measure_shift
        before = dark_profile(r)
        mouse.scroll(coords=(r.left + r.width() // 2, r.top + r.height() // 2), wheel_dist=-notches)
        time.sleep(0.9)
        return measure_shift(before, dark_profile(r))

    def _rows_visible(self, r):
        return max(1, (r.height() - ROW_Y0 - 6) // ROW_H + 1)

    def rename_and_address(self, mapping):
        """mapping: {current name of station: (new name, ip)}. One pass down the Device Table (the names are
        read on every row, so a row is identified before it is edited), then one pass down the IP Address Table
        by the same row positions. Returns the names it could not find."""
        self.select_page(DEVICE_TABLE_PAGE)
        r = self._grid(DEVICE_TABLE_ID)
        visible = self._rows_visible(r)
        order = []                  # (absolute row index, current name) in table order
        scrolled = 0
        pending = dict(mapping)
        px_per_notch = None
        while True:
            first_abs = -(-scrolled // ROW_H)                       # the first fully visible absolute row
            page_rows = 0
            for k in range(visible + 1):
                abs_row = first_abs + k
                y = ROW_Y0 + ROW_H * abs_row - scrolled
                if y < ROW_Y0 - 4 or y > r.height() - 10:
                    continue
                if any(a == abs_row for a, _ in order):
                    continue
                mouse.click(coords=(r.left + self.cx(NAME_X), r.top + y))
                time.sleep(0.7)
                eds = self.controls(("Edit",), cid=NAME_EDIT_ID)
                if not eds:
                    page_rows = -1
                    break
                name = eds[0].window_text()
                order.append((abs_row, name))
                page_rows += 1
                if name in pending:
                    new, _ip = pending.pop(name)
                    eds[0].select()
                    time.sleep(0.2)
                    keyboard.send_keys(new, with_spaces=True)
                    time.sleep(0.3)
                    mouse.click(coords=(r.left + self.cx(COMMIT_X), r.top + y))
                    time.sleep(0.7)
                    mouse.click(coords=(r.left + self.cx(NAME_X), r.top + y))
                    time.sleep(0.7)
                    value = self.controls(("Edit",), cid=NAME_EDIT_ID)[0].window_text()
                    mouse.click(coords=(r.left + self.cx(COMMIT_X), r.top + y))
                    time.sleep(0.4)
                    if value.lower() != new.lower():          # SYCON.net lower-cases a name of station
                        raise SyconError("row %d: name reads %r after writing %r" % (abs_row, value, new))
                    log("  row %d: %s -> %s" % (abs_row, name, new))
            if page_rows < 0 or not pending:
                break
            notches = 3 if px_per_notch is None else max(1, int((visible - 2) * ROW_H / px_per_notch))
            shift = self._scroll(r, notches)
            if shift <= 0:
                break
            if px_per_notch is None:
                px_per_notch = shift / notches
            scrolled += shift
        if pending:
            log("  not found in the Device Table:", sorted(pending))
        mouse.click(coords=(r.left + self.cx(COMMIT_X), r.top + ROW_Y0))
        time.sleep(0.4)
        # the IPs, by the same absolute rows - in TWO passes, because a target IP may still be held by another
        # row's auto-assigned address: first every row to a parking address, then the targets. Each row's current
        # IP is checked against the expected one before it is written (the row identity on this page).
        self.select_page(IP_TABLE_PAGE)
        r = self._grid(IP_TABLE_ID)
        rows = [(abs_row, name) for abs_row, name in order if name in mapping]
        parking = {}
        for i, (abs_row, name) in enumerate(rows):
            new, ip = mapping[name]
            parking[abs_row] = "%s.%d" % (".".join(ip.split(".")[:3]), 200 + i % 55)
        expected = dict(self.expected_ips or {})
        for phase_name, targets in (("park", {a: (n, parking[a]) for a, n in rows}),
                                    ("target", {a: mapping[n] for a, n in rows})):
            targets = dict(targets)
            scrolled = 0
            px_per_notch = None
            while targets:
                page = sorted(a for a in targets if ROW_Y0 - 4 <= ROW_Y0 + ROW_H * a - scrolled <= r.height() - 10)
                for abs_row in page:
                    y = ROW_Y0 + ROW_H * abs_row - scrolled
                    new, ip = targets.pop(abs_row)
                    before = self._set_ip_at(r, y, ip, "%s row %d (%s)" % (phase_name, abs_row, new), expect=expected.get(abs_row))
                    expected[abs_row] = ip
                    if phase_name == "park":
                        log("  row %d auto IP was %s" % (abs_row, before))
                if not targets:
                    break
                notches = 3 if px_per_notch is None else max(1, int((visible - 2) * ROW_H / px_per_notch))
                shift = self._scroll(r, notches)
                if shift <= 0:
                    raise SyconError("the IP Address Table did not scroll; rows left: %r" % sorted(targets))
                if px_per_notch is None:
                    px_per_notch = shift / notches
                scrolled += shift
            if phase_name == "park":
                self._scroll(r, -200)                     # back to the top for the second pass
        return sorted(pending)

    expected_ips = None       # {absolute row: the IP the row must show before it is written} - set by the caller

    def _set_ip_at(self, r, y, ip, label, expect=None):
        mouse.click(coords=(r.left + self.cx(IP_X), r.top + y))
        time.sleep(0.8)
        ipc = self.controls(("SysIPAddress32",))
        if not ipc:
            raise SyconError("no IP editor at %s" % label)
        before = ".".join(f.window_text() for f in sorted(ipc[0].children(), key=lambda c: c.rectangle().left))
        if expect and before != expect:
            mouse.click(coords=(r.left + self.cx(IP_COMMIT_X), r.top + y))
            raise SyconError("%s shows IP %s, expected %s - row mismatch, nothing written" % (label, before, expect))
        _set_ip_control(ipc[0], ip)
        mouse.click(coords=(r.left + self.cx(IP_COMMIT_X), r.top + y))
        time.sleep(0.8)
        mouse.click(coords=(r.left + self.cx(IP_X), r.top + y))
        time.sleep(0.8)
        ipc = self.controls(("SysIPAddress32",))
        after = ".".join(f.window_text() for f in sorted(ipc[0].children(), key=lambda c: c.rectangle().left)) if ipc else ""
        mouse.click(coords=(r.left + self.cx(IP_COMMIT_X), r.top + y))
        time.sleep(0.4)
        log("  IP at %s: %s -> %s" % (label, before, after))
        if after != ip:
            raise SyconError("IP reads %s after writing %s at %s" % (after, ip, label))
        return before

    # ---- IP Address Table ---------------------------------------------------------------------------------
    def set_station_ip(self, row_y, ip):
        self.select_page(IP_TABLE_PAGE)
        r = self._grid(IP_TABLE_ID)
        mouse.click(coords=(r.left + self.cx(IP_X), r.top + row_y))
        time.sleep(0.9)
        ipc = self.controls(("SysIPAddress32",))
        if not ipc:
            raise SyconError("no IP editor on row y+%d" % row_y)
        before = ".".join(f.window_text() for f in sorted(ipc[0].children(), key=lambda c: c.rectangle().left))
        _set_ip_control(ipc[0], ip)
        mouse.click(coords=(r.left + self.cx(IP_COMMIT_X), r.top + row_y))   # commit
        time.sleep(0.9)
        mouse.click(coords=(r.left + self.cx(IP_X), r.top + row_y))          # verify
        time.sleep(0.9)
        ipc = self.controls(("SysIPAddress32",))
        after = ".".join(f.window_text() for f in sorted(ipc[0].children(), key=lambda c: c.rectangle().left))
        mouse.click(coords=(r.left + self.cx(IP_COMMIT_X), r.top + row_y))
        time.sleep(0.6)
        log("  IP Address Table row y+%d: %s -> %s" % (row_y, before, after))
        if after != ip:
            raise SyconError("IP reads %s after writing %s" % (after, ip))
