"""The SYCON.net process and its windows: launch, login, main window, dialogs, message boxes, commands.

Facts this module encodes (proved on the VM, 2026-10-23):
- the login dialog `SYCON.net User Login` takes empty credentials: press OK;
- the main window is `SYCON.net - [<project>.spj]`; its File commands are MFC ids posted as WM_COMMAND;
- every DTM dialog and message box is a #32770 window OWNED by the main window: UI Automation lists it under
  the main window, so top-level windows are enumerated through win32 and wrapped for UIA by handle;
- a popup menu can take seconds to appear; a click meant for the tree would land on it;
- never post a command to the main window while a modal dialog is open (PostMessage bypasses modality);
- SYCON.net can exit silently: check the process after every drop and dialog close.
"""
import ctypes
import os
import subprocess
import time
from ctypes import wintypes

from pywinauto import Desktop, keyboard

EXE = r"C:\Program Files (x86)\Hilscher GmbH\SYCONnet\Syconu.exe"
WM_COMMAND = 0x0111
COMMANDS = {"new": 57600, "open": 57601, "close": 57602, "save": 57603, "save_as": 57604, "exit": 57665}
BUTTON_IDS = {"OK": 1, "Cancel": 2, "Yes": 6, "No": 7, "Help": 9}
SKIP_CLASSES = ("tooltips_class32", "MSCTFIME UI", "IME", "ComboLBox")
user32 = ctypes.windll.user32


class SyconError(RuntimeError):
    pass


def log(*parts):
    print(time.strftime("%H:%M:%S"), *parts, flush=True)


def sycon_pids():
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Syconu.exe", "/FO", "CSV", "/NH"],
                         capture_output=True, text=True).stdout
    return [int(line.split('","')[1]) for line in out.splitlines() if line.startswith('"Syconu.exe"')]


def pid_at_point(x, y):
    h = user32.WindowFromPoint(wintypes.POINT(int(x), int(y)))
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
    return h, pid.value


def uia():
    return Desktop(backend="uia")


def win32():
    return Desktop(backend="win32")


class Session:
    """One running SYCON.net."""

    def __init__(self):
        self.pid = None

    # ---- process ------------------------------------------------------------------------------------------
    def attach(self):
        pids = sycon_pids()
        if not pids:
            raise SyconError("SYCON.net is not running")
        self.pid = pids[0]
        return self

    def attach_if_running(self):
        pids = sycon_pids()
        if pids:
            self.pid = pids[0]
        return bool(pids)

    def is_alive(self):
        return self.pid is not None and self.pid in sycon_pids()

    def ensure_alive(self, what=""):
        if not self.is_alive():
            raise SyconError("SYCON.net exited" + (" after " + what if what else ""))

    def launch(self, project=None, timeout=120.0):
        """Start SYCON.net (optionally on a project) and wait for the login dialog."""
        if sycon_pids():
            raise SyconError("SYCON.net already running; close it first")
        args = [EXE] + ([project] if project else [])
        subprocess.Popen(args, cwd=os.path.dirname(EXE))
        t0 = time.time()
        while time.time() - t0 < timeout:
            time.sleep(2.0)
            for w in uia().windows():
                if w.window_text() == "SYCON.net User Login" or any(
                        c.window_text() == "SYCON.net User Login" for c in w.children()):
                    self.pid = w.process_id()
                    return self
        raise SyconError("the login dialog did not appear")

    def login(self, timeout=60.0):
        """Press OK on the login dialog (empty credentials) and wait for the main window."""
        login = None
        for w in uia().windows():
            if w.window_text() == "SYCON.net User Login":
                login = w
            else:
                for c in w.children():
                    if c.window_text() == "SYCON.net User Login":
                        login = c
        if login is None:
            raise SyconError("no login dialog")
        [b for b in login.descendants(control_type="Button") if b.window_text() == "OK"][0].click_input()
        t0 = time.time()
        while time.time() - t0 < timeout:
            time.sleep(2.0)
            for w in uia().windows():
                if w.window_text().startswith("SYCON.net") and w.process_id() == self.pid and w.descendants(control_type="Tree"):
                    time.sleep(3.0)
                    return w
        raise SyconError("the main window did not appear")

    def close(self, timeout=30.0):
        """Close SYCON.net WITHOUT saving: WM_CLOSE to its own main window (never a key to the foreground window),
        answer No to the save prompt, kill if stuck."""
        if not self.is_alive():
            return "not running"
        self.dismiss_errors()
        self.close_menus()
        try:
            user32.PostMessageW(self.main().handle, 0x0010, 0, 0)        # WM_CLOSE
        except Exception:  # noqa: BLE001
            pass
        t0 = time.time()
        while time.time() - t0 < timeout:
            time.sleep(1.0)
            if not self.is_alive():
                return "closed"
            for w in self.top_windows():
                if w.window_text() in ("SYCON.net", "Save", "Confirm", "Question"):
                    self.click_button(w, "No")
        subprocess.run(["taskkill", "/PID", str(self.pid), "/F"], capture_output=True)
        time.sleep(2.0)
        return "killed"

    # ---- windows ------------------------------------------------------------------------------------------
    def main(self):
        for w in uia().windows():
            if w.process_id() == self.pid and w.window_text().startswith("SYCON.net") and w.class_name().startswith("Afx"):
                return w
        raise SyconError("no SYCON.net main window")

    def title(self):
        return self.main().window_text()

    def bring_front(self):
        """Put the main window above everything (the Claude app window covers it when the user is away): the
        window is made TOPMOST for the session (clicks then reach it; a click also gives it the keyboard focus),
        SetForegroundWindow is attempted on top of that (Windows may refuse it to a background process - fine).
        Verified by the pixel owner at two points. No key is ever sent to an unknown foreground window."""
        import win32con
        import win32gui
        main = self.main()
        hwnd = main.handle
        flags = win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE
        for attempt in range(3):
            try:
                if win32gui.IsIconic(hwnd):
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0, flags)
            except Exception as ex:  # noqa: BLE001
                log("bring_front: SetWindowPos failed:", ex)
            try:
                win32gui.SetForegroundWindow(hwnd)
            except Exception:  # noqa: BLE001 - refused to a background process; TOPMOST is enough for the clicks
                pass
            time.sleep(0.5)
            r = main.rectangle()
            h, owner = pid_at_point((r.left + r.right) // 2, (r.top + r.bottom) // 2)
            h2, owner2 = pid_at_point(r.right - 300, r.top + 300)      # the catalog side
            if owner == self.pid and owner2 == self.pid:
                return
            time.sleep(1.0)
        raise SyconError("SYCON.net cannot be brought in front (pid %d / %d covers it)" % (owner, owner2))

    def top_windows(self):
        """Visible top-level windows of the process (win32 enumeration), as UIA wrappers."""
        out = []
        for w in win32().windows(process=self.pid, visible_only=True):
            if w.class_name() in SKIP_CLASSES:
                continue
            try:
                out.append(uia().window(handle=w.handle).wrapper_object())
            except Exception:  # noqa: BLE001
                pass
        return out

    def boxes(self, title):
        """Message boxes (#32770) with this title, as win32 wrappers."""
        return [w for w in win32().windows(process=self.pid, visible_only=True)
                if w.class_name() == "#32770" and w.window_text() == title]

    def dialogs(self, title_sub="Configuration"):
        """Open DTM dialogs (#32770 with the substring in the title), as UIA wrappers."""
        return [w for w in self.top_windows() if w.class_name() == "#32770" and title_sub in w.window_text()]

    def modal_open(self):
        return [w.window_text()[:40] for w in self.top_windows() if w.class_name() == "#32770"]

    @staticmethod
    def click_button(window, name):
        """Click a button of a win32/UIA window by its name through a win32 BM_CLICK (no mouse)."""
        w32w = win32().window(handle=window.handle)
        for b in w32w.descendants(class_name="Button"):
            if b.window_text().replace("&", "") == name and b.is_visible():
                b.click()
                time.sleep(1.0)
                return True
        return False

    def dismiss_errors(self, max_n=50):
        """Press OK on every modal 'Error' box (they stack). Returns their texts."""
        texts = []
        for _ in range(max_n):
            errs = self.boxes("Error")
            if not errs:
                break
            w = errs[0]
            texts.append(" / ".join(c.window_text() for c in w.children() if c.class_name() == "Static" and c.window_text()))
            if not self.click_button(w, "OK"):
                w.close()
            time.sleep(0.8)
        return texts

    def answer_box(self, title, button, timeout=6.0):
        """Answer a message box (Warning, Question, ...) with a named button; returns its text or None."""
        t0 = time.time()
        while time.time() - t0 < timeout:
            for w in self.boxes(title):
                text = " / ".join(c.window_text()[:120] for c in w.children() if c.class_name() == "Static" and c.window_text())
                self.click_button(w, button)
                time.sleep(1.0)
                return text
            time.sleep(0.5)
        return None

    # ---- menus and clicks -----------------------------------------------------------------------------------
    @staticmethod
    def popup_menus():
        return [w for w in uia().windows() if w.element_info.control_type == "Menu" or w.class_name() == "#32768"]

    def wait_menu(self, timeout=15.0):
        t0 = time.time()
        while time.time() - t0 < timeout:
            m = self.popup_menus()
            if m:
                time.sleep(0.3)
                return m[0]
            time.sleep(0.25)
        return None

    def close_menus(self, timeout=5.0):
        t0 = time.time()
        while self.popup_menus():
            keyboard.send_keys("{ESC}")
            time.sleep(0.5)
            if time.time() - t0 > timeout:
                return not self.popup_menus()
        return True

    def safe_click(self, element, button="left", double=False, allow_menu=False):
        """Click an element's mid point only when no popup menu is open (unless the target IS a menu item) and
        the pixel there belongs to SYCON.net (the Claude window can overlap)."""
        if not allow_menu and self.popup_menus():
            raise SyconError("a popup menu is open; not clicking")
        p = element.rectangle().mid_point()
        h, owner = pid_at_point(p.x, p.y)
        if owner != self.pid:
            raise SyconError("(%d,%d) is covered by another process (pid %d); not clicking" % (p.x, p.y, owner))
        if double:
            element.double_click_input()
        else:
            element.click_input(button=button)

    # ---- commands -----------------------------------------------------------------------------------------
    def post_command(self, name):
        """Post a File command to the main window. Refused while a modal dialog is open."""
        self.post_command_id(COMMANDS[name], name)

    def post_command_id(self, command_id, label=""):
        """Post an MFC command id (a menu / context-menu entry) to the main window; refused while modal."""
        open_ = self.modal_open()
        if open_:
            raise SyconError("modal dialog open, command %r refused: %r" % (label or command_id, open_))
        main = self.main()
        if not main.is_enabled():
            raise SyconError("main window disabled, command %r refused" % (label or command_id))
        user32.PostMessageW(main.handle, WM_COMMAND, command_id, 0)

    # ---- the netProject tree --------------------------------------------------------------------------------
    @staticmethod
    def _iter_items(element):
        for c in element.children():
            if c.element_info.control_type == "TreeItem":
                yield c
            yield from Session._iter_items(c)

    def project_tree(self):
        """The netProject tree = the Tree whose root item is `Project: <name>` (only the root is looked at: walking
        every item of the device catalog tree instead cost 15-30 s per call, 2026-10-23)."""
        for t in self.main().descendants(control_type="Tree"):
            first = [c for c in t.children() if c.element_info.control_type == "TreeItem"][:1]
            if first and first[0].window_text().startswith("Project:"):
                return t
        raise SyconError("netProject tree not found")

    def nodes(self):
        try:
            return [i.window_text() for i in self._iter_items(self.project_tree())]
        except SyconError:
            return []

    def station_item(self, station):
        want = "<%s>" % station.lower()                  # SYCON.net lower-cases a name of station
        for i in self._iter_items(self.project_tree()):
            if want in i.window_text().lower():
                return i
        raise SyconError("station <%s> not in the netProject tree" % station)

    def catalog_tree(self):
        trees = [t for t in self.main().descendants(control_type="Tree") if t.element_info.automation_id == "40000"]
        if not trees:
            raise SyconError("device catalog tree not found")
        return trees[0]

    @staticmethod
    def same_text(a, b):
        """SYCON.net texts compared with their spacing collapsed (`IO-Link In/Out  2/ 2 Byte + PQI`), case ignored."""
        return " ".join(str(a).split()).lower() == " ".join(str(b).split()).lower()

    def catalog_info(self):
        """The text of the info pane under the device catalog (RichEdit20W 59664): the DTM and the device the
        selected catalog item stands for - its GSDML file cited in brackets, `[GSDML-V2.35-Siemens-PNPNIOC-
        20200924.xml]`. Empty when nothing is selected."""
        for e in self.main().descendants(class_name="RichEdit20W"):
            if e.element_info.automation_id == "59664":
                try:
                    return e.get_value() or ""
                except Exception:
                    return (e.legacy_properties() or {}).get("Value", "") or ""
        return ""

    def output_log(self):
        out = []
        for lst in self.main().descendants(control_type="List"):
            for it in lst.children():
                out.append(it.window_text())
        return out
