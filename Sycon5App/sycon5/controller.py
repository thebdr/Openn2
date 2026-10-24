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


def _ip_key(ip):
    """An IPv4 address as a tuple of ints (the IP Address Table's order); a malformed one sorts last."""
    try:
        return tuple(int(x) for x in str(ip).split("."))
    except ValueError:
        return (999, 999, 999, 999)


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
            offered = upd.item_texts()
            if want not in offered:
                # the device's own range (a SCALANCE: 128 / 256 / 512 ms, 2026-10-23 21:36): the smallest offered
                # at or above the wanted value, else the largest
                nums = sorted((float(x), x) for x in offered if x.replace(".", "", 1).isdigit())
                if not nums:
                    raise SyconError("updating time %r not offered for %s: %r" % (want, st, offered))
                pick = next((x for v, x in nums if v >= float(ms)), nums[-1][1])
                log("  timing %s: %s ms not offered (%r) - %s ms taken" % (st, want, offered, pick))
                want = pick
            if upd.selected_text() != want:
                upd.select(want)
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
        # the shift is measured on the overlap of the two captures: a grid of alike rows aliases at a row's pitch,
        # and a shift beyond two thirds of the view leaves too little overlap to tell (2026-10-24 17:12: rows 60 and
        # 61 of 62 taken for 99 and 100) - the pages are scrolled by HALF a view and the search capped there
        return measure_shift(before, dark_profile(r), max_shift=r.height() * 2 // 3)

    def _rows_visible(self, r):
        return max(1, (r.height() - ROW_Y0 - 6) // ROW_H + 1)

    def rename_and_address(self, mapping, current_ips=None):
        """mapping: {current name of station: (new name, ip)}. One pass down the Device Table (the names are
        read on every row, so a row is identified before it is edited), then one pass down the IP Address Table
        by the same row positions. `current_ips` = {current name: the IP its row shows now} as far as the caller
        knows (a resume knows every saved station's): the row identity check of the IP pass. After every scroll
        both passes find a row they know again and correct the scroll offset by whole rows (the pixel-measured
        shift of a grid of alike rows is ambiguous: 2026-10-24 17:19 the IPs of rows 60 / 61 were written on rows
        57 / 58). Returns the names it could not find."""
        current_ips = dict(current_ips or {})
        self.phase = "names"        # the caller's failure policy: the names pass is all-or-nothing, the IP pass keeps
        self.select_page(DEVICE_TABLE_PAGE)
        r = self._grid(DEVICE_TABLE_ID)
        visible = self._rows_visible(r)
        order = []                  # (absolute row index, current name) in table order
        scrolled = 0
        pending = dict(mapping)
        px_per_notch = None
        def sweep(at_end):
            """Visit the rows shown (read the name, rename the wanted ones); -1 when a click opens no editor.
            At the table's END the last row's centre may sit inside the bottom margin (2026-10-24: station 60
            of 60 of the sorter build was never visited): the margin shrinks from 10 px to 3, the click capped."""
            first_abs = -(-scrolled // ROW_H)                       # the first fully visible absolute row
            page_rows = 0
            for k in range(visible + 2):
                abs_row = first_abs + k
                y = ROW_Y0 + ROW_H * abs_row - scrolled
                if y < ROW_Y0 - 4 or y > r.height() - (3 if at_end else 10):
                    continue
                if any(a == abs_row for a, _ in order):
                    continue
                y = min(y, r.height() - 4)
                mouse.click(coords=(r.left + self.cx(NAME_X), r.top + y))
                time.sleep(0.7)
                eds = self.controls(("Edit",), cid=NAME_EDIT_ID)
                if not eds:
                    return -1
                name = eds[0].window_text()
                order.append((abs_row, name))
                page_rows += 1
                if name in pending:
                    new, _ip = pending.pop(name)
                    if new.lower() == name.lower():                 # an IP-only row (a resume re-addressing it)
                        log("  row %d: %s keeps its name" % (abs_row, name))
                        continue
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
            return page_rows

        while True:
            page_rows = sweep(False)
            if page_rows < 0 or not pending:
                break
            notches = 3 if px_per_notch is None else max(1, int((visible // 2) * ROW_H / px_per_notch))
            shift = self._scroll(r, notches)
            if shift <= 0:
                sweep(True)                                         # the table's end: its bottom row
                break
            if px_per_notch is None:
                px_per_notch = shift / notches
            scrolled += shift
            if order:                                               # the last row visited: where is it now?
                scrolled = self._resync(r, scrolled, order[-1][0], order[-1][1], self._read_name_at)
        if pending:
            log("  not found in the Device Table:", sorted(pending))
        mouse.click(coords=(r.left + self.cx(COMMIT_X), r.top + ROW_Y0))
        time.sleep(0.4)
        # the IPs: the IP Address Table has its own row order (see below), one pass straight to the targets
        self.phase = "ips"
        self.select_page(IP_TABLE_PAGE)
        r = self._grid(IP_TABLE_ID)
        # the IP Address Table lists the stations SORTED BY IP, not in the Device Table's order (2026-10-24 17:19-17:30:
        # the Device Table's rows 60 / 61 - two new stations with the auto IPs .3 / .4 - were this table's rows 1 / 2,
        # and 'rows 60 / 61' here held the two highest IPs), and its rows do not move while the dialog is open. A
        # read-only scan gives each row's IP; a station's row is the row of its CURRENT IP: the saved one the caller
        # knows (a resume), else an auto-assigned one - the IPs of the scan no known station holds, ascending, given
        # to the new stations in Device Table order (SYCON.net assigns the next free address at every add / paste).
        # Every write reads the row's IP first and refuses a row that does not show the expected one.
        ip_rows = self._scan_ips(r, visible)
        self._scroll(r, -200)                                 # the scan ends at the bottom: back to the top
        known = {n: ip for n, ip in current_ips.items() if ip}
        unclaimed = sorted((ip for ip in ip_rows if ip not in set(known.values())), key=_ip_key)
        for _abs_row, name in order:
            if name not in known and unclaimed:
                known[name] = unclaimed.pop(0)
        rows = []
        for name in mapping:
            if name not in known or known[name] not in ip_rows:
                raise SyconError("station %r: its current IP %r is not in the IP Address Table (%d rows)"
                                 % (name, known.get(name), len(ip_rows)))
            rows.append((ip_rows.index(known[name]), name))
        rows.sort()
        log("  IP Address Table: %d rows scanned; the %d stations to address sit at rows %s" % (
            len(ip_rows), len(rows), [a for a, _n in rows]))
        # ONE pass down the table, every row straight to its target (user 2026-10-24: "duplicate ip addresses raise
        # an error only on save, i think we can drop the n.n.n.200+ pre-filling if we do the ip address fill in one
        # run" - a target still held by another row is fine until OK, by when that row has its own)
        expected = dict(self.expected_ips or {})
        for abs_row, name in rows:
            expected[abs_row] = known[name]
        targets = {a: mapping[n] for a, n in rows}
        scrolled = 0
        px_per_notch = None
        margin = 10                 # the bottom margin; 3 at the table's end (its last row's centre may sit in it)
        last = None                 # the last row written: (abs row, its IP) - the resync anchor after a scroll
        while targets:
            page = sorted(a for a in targets if ROW_Y0 - 4 <= ROW_Y0 + ROW_H * a - scrolled <= r.height() - margin)
            for abs_row in page:
                y = min(ROW_Y0 + ROW_H * abs_row - scrolled, r.height() - 4)
                new, ip = targets.pop(abs_row)
                before = self._set_ip_at(r, y, ip, "row %d (%s)" % (abs_row, new), expect=expected.get(abs_row))
                expected[abs_row] = ip
                last = (abs_row, ip)
            if not targets:
                break
            if margin == 3:
                raise SyconError("the IP Address Table did not scroll; rows left: %r" % sorted(targets))
            notches = 3 if px_per_notch is None else max(1, int((visible // 2) * ROW_H / px_per_notch))
            shift = self._scroll(r, notches)
            if shift <= 0:
                margin = 3
                continue
            if px_per_notch is None:
                px_per_notch = shift / notches
            scrolled += shift
            if last is not None:
                scrolled = self._resync(r, scrolled, last[0], last[1], self._read_ip_at)
        return sorted(pending)

    def _scan_ips(self, r, visible):
        """Every row's IP of the IP Address Table, top to bottom - a read-only pass, the scroll re-synchronised on
        the last row read; stops at the first row that opens no editor (below the table)."""
        ips, scrolled, px_per_notch, at_end = [], 0, None, False
        while True:
            first_abs = -(-scrolled // ROW_H)
            for k in range(visible + 2):
                abs_row = first_abs + k
                if abs_row < len(ips):
                    continue
                if abs_row > len(ips):
                    break
                y = ROW_Y0 + ROW_H * abs_row - scrolled
                if y < ROW_Y0 - 4 or y > r.height() - (3 if at_end else 10):
                    continue
                ip = self._read_ip_at(r, min(y, r.height() - 4))
                if not ip:
                    return ips
                ips.append(ip)
            if at_end:
                return ips
            notches = 3 if px_per_notch is None else max(1, int((visible // 2) * ROW_H / px_per_notch))
            shift = self._scroll(r, notches)
            if shift <= 0:
                at_end = True
                continue
            if px_per_notch is None:
                px_per_notch = shift / notches
            scrolled += shift
            if ips:
                scrolled = self._resync(r, scrolled, len(ips) - 1, ips[-1], self._read_ip_at)

    def _resync(self, r, scrolled, known_abs, known_value, read_at):
        """The scroll offset corrected on a known row: it should sit at y = ROW_Y0 + ROW_H * abs - scrolled; read
        there and up to 8 rows either side until its value shows; the offset moves by whole rows."""
        for k in (0, 1, -1, 2, -2, 3, -3, 4, -4, 5, -5, 6, -6, 7, -7, 8, -8):
            y = ROW_Y0 + ROW_H * known_abs - scrolled + k * ROW_H
            if y < ROW_Y0 - 4 or y > r.height() - 4:
                continue
            if read_at(r, y) == known_value:
                if k:
                    log("  scroll resync: row %d (%s) sits %+d rows from where the measured shift put it" % (known_abs, known_value, k))
                return scrolled - k * ROW_H
        raise SyconError("scroll lost: row %d (%s) not found within 8 rows of its place" % (known_abs, known_value))

    def _read_name_at(self, r, y):
        mouse.click(coords=(r.left + self.cx(NAME_X), r.top + y))
        time.sleep(0.7)
        eds = self.controls(("Edit",), cid=NAME_EDIT_ID)
        value = eds[0].window_text() if eds else ""
        mouse.click(coords=(r.left + self.cx(COMMIT_X), r.top + y))
        time.sleep(0.4)
        return value

    def _read_ip_at(self, r, y):
        mouse.click(coords=(r.left + self.cx(IP_X), r.top + y))
        time.sleep(0.8)
        ipc = self.controls(("SysIPAddress32",))
        value = ".".join(f.window_text() for f in sorted(ipc[0].children(), key=lambda c: c.rectangle().left)) if ipc else ""
        mouse.click(coords=(r.left + self.cx(IP_COMMIT_X), r.top + y))
        time.sleep(0.4)
        return value

    expected_ips = None       # {absolute row: the IP the row must show before it is written} - set by the caller

    def _open_ip_editor(self, r, y, label):
        """Click the IP cell until its in-place SysIPAddress32 editor is there (2026-10-24 04:48: one verify click
        of 120 opened none within 0.8 s and the whole pass was lost) - three attempts, each waiting longer."""
        for attempt in range(3):
            mouse.click(coords=(r.left + self.cx(IP_X), r.top + y))
            time.sleep(0.8 + 0.7 * attempt)
            ipc = self.controls(("SysIPAddress32",))
            if ipc:
                return ipc[0]
            log("  no IP editor at %s (attempt %d)" % (label, attempt + 1))
        raise SyconError("no IP editor at %s" % label)

    def _set_ip_at(self, r, y, ip, label, expect=None):
        ipc = self._open_ip_editor(r, y, label)
        before = ".".join(f.window_text() for f in sorted(ipc.children(), key=lambda c: c.rectangle().left))
        if expect and before != expect:
            mouse.click(coords=(r.left + self.cx(IP_COMMIT_X), r.top + y))
            raise SyconError("%s shows IP %s, expected %s - row mismatch, nothing written" % (label, before, expect))
        _set_ip_control(ipc, ip)
        mouse.click(coords=(r.left + self.cx(IP_COMMIT_X), r.top + y))
        time.sleep(0.8)
        ipc = self._open_ip_editor(r, y, label + " (verify)")
        after = ".".join(f.window_text() for f in sorted(ipc.children(), key=lambda c: c.rectangle().left))
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
