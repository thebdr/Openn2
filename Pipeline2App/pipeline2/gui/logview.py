"""logview.py - a self-contained, colour-coded log widget shared by the GUIs.

`LogView` is a `ttk.Frame` wrapping a read-only `tk.Text` with severity colours, clickable
`[open Sheet!Cell]` links (jump into Excel via pywin32), and a thread-safe queue + drain pump.
Worker threads call `log()/section()/post_status()/post_busy()`; the drain renders on the main
thread and forwards status/busy to the host App's callbacks.

This is the extraction of gui.py's log machinery so gui_designer.py reuses it verbatim.
"""
from __future__ import annotations
import os
import queue
import threading
import tkinter as tk
from tkinter import ttk

from pipeline2.gui import theme

LOG_LEVELS = {"ERROR", "FAIL", "WARNING", "PASS", "SKIP", "OK", "INFO", "SECTION"}


# --------------------------------------------------------------------------- #
# Excel cell-jump (pywin32 COM; degrades gracefully without it)               #
# --------------------------------------------------------------------------- #
def _bring_to_front(hwnd: int) -> None:
    """Force a window to the foreground, working around Windows' focus lock."""
    import win32api
    import win32con
    import win32gui
    import win32process
    if not hwnd:
        return
    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    fg = win32gui.GetForegroundWindow()
    cur = win32api.GetCurrentThreadId()
    other = win32process.GetWindowThreadProcessId(fg)[0] if fg else 0
    attached = bool(other) and other != cur
    if attached:
        win32process.AttachThreadInput(other, cur, True)
    try:
        win32gui.BringWindowToTop(hwnd)
        win32gui.SetForegroundWindow(hwnd)
    finally:
        if attached:
            win32process.AttachThreadInput(other, cur, False)


def excel_goto(path: str, sheet: str, cell: str) -> tuple[bool, str]:
    """Open `path` in Excel at `sheet!cell` (reusing a running instance); fall back to just
    opening the workbook if pywin32 is missing. Runs on a worker thread (COM init/teardown)."""
    if not path or not os.path.exists(path):
        return False, f"workbook not found: {path}"
    try:
        import pythoncom
        import win32com.client as win32
    except ImportError:
        try:
            os.startfile(path)  # type: ignore[attr-defined]
            return False, f"opened workbook - press Ctrl+G -> {sheet}!{cell} (install pywin32 for the cell jump)"
        except Exception as e:  # noqa: BLE001
            return False, f"could not open {path}: {e}"

    pythoncom.CoInitialize()
    try:
        try:
            xl = win32.GetActiveObject("Excel.Application")
        except Exception:  # noqa: BLE001 - no running instance, start one
            xl = win32.Dispatch("Excel.Application")
        xl.Visible = True
        full = os.path.abspath(path)
        wb = None
        for b in xl.Workbooks:
            try:
                if os.path.normcase(b.FullName) == os.path.normcase(full):
                    wb = b
                    break
            except Exception:  # noqa: BLE001
                pass
        if wb is None:
            wb = xl.Workbooks.Open(full)
        ws = wb.Worksheets(sheet)
        ws.Activate()
        xl.Goto(ws.Range(cell), True)
        try:
            _bring_to_front(int(xl.Hwnd))
        except Exception:  # noqa: BLE001 - focus is best-effort
            try:
                xl.ActiveWindow.Activate()
            except Exception:  # noqa: BLE001
                pass
        return True, f"Excel -> {sheet}!{cell}"
    except Exception as e:  # noqa: BLE001
        return False, f"Excel COM error: {e}"
    finally:
        pythoncom.CoUninitialize()


# --------------------------------------------------------------------------- #
# the widget                                                                  #
# --------------------------------------------------------------------------- #
class LogView(ttk.Frame):
    """Colour-coded, link-aware, thread-safe log pane.

    on_status(text) / on_busy(bool): optional callbacks invoked on the main thread by the
    drain loop (so the host App can update a status bar / disable buttons)."""

    def __init__(self, parent, on_status=None, on_busy=None, font_size: int = 10):
        super().__init__(parent)
        self._on_status = on_status
        self._on_busy = on_busy
        self._font_size = font_size
        self.q: queue.Queue = queue.Queue()
        self._links: dict[str, dict] = {}
        self._lnk = 0
        self._error_csv = None        # the current run's error_management.csv ([FAIL] tag links to it)

        self.text = tk.Text(self, wrap="word", font=("Consolas", font_size), undo=False)
        ys = ttk.Scrollbar(self, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=ys.set)
        ys.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)
        self.text.bind("<Key>", self._readonly_keys)
        # the [FAIL] tag is a single shared "errlink" (underline only, keeps the FAIL colour);
        # the binding reads self._error_csv live, so it always opens the latest run's registry.
        self.text.tag_configure("errlink", underline=True)
        self.text.tag_bind("errlink", "<Button-1>", lambda e: self._open_file(self._error_csv))
        self.text.tag_bind("errlink", "<Enter>", lambda e: self.text.config(cursor="hand2"))
        self.text.tag_bind("errlink", "<Leave>", lambda e: self.text.config(cursor=""))
        self.after(60, self._drain)

    # ---- theming ---- #
    def apply_theme(self, pal: dict, dark: bool, base: int | None = None) -> None:
        base = base if base is not None else self._font_size
        self.text.configure(background=pal["log_bg"], foreground=pal["log_fg"],
                            insertbackground=pal["log_fg"], font=("Consolas", base))
        for level, cfg in theme.log_tags(dark).items():
            cfg = dict(cfg)
            if "font" in cfg:                          # keep each tag's relative size/style
                fam, sz, *style = cfg["font"]
                cfg["font"] = (fam, base + (sz - 10), *style)
            self.text.tag_configure(level, **cfg)
        self.text.tag_configure("link", foreground=pal["accent"], underline=True)

    # ---- thread-safe producers ---- #
    def log(self, level: str, text: str, link: dict | None = None) -> None:
        self.q.put(("log", level, text, link))

    def section(self, title: str) -> None:
        self.q.put(("log", "SECTION", title, None))

    def log_line(self, level, location, body, link1=None, link2=None) -> None:
        """A structured validation line: a leading clickable cell (link1), an aligned body, and
        an optional trailing other-workbook link (link2). Used for the cross-check / info-block lines."""
        self.q.put(("logline", level, location, body, link1, link2))

    def set_error_link(self, path) -> None:
        """Point the [FAIL] tag at this run's error_management.csv (call before rendering)."""
        self.q.put(("errlink", path))

    def post_status(self, text: str) -> None:
        self.q.put(("status", text))

    def post_busy(self, busy: bool) -> None:
        self.q.put(("busy", busy))

    def clear(self) -> None:
        self.q.put(("clear", None))

    # ---- main-thread rendering ---- #
    def _readonly_keys(self, event):
        if (event.state & 0x4) and event.keysym.lower() in ("c", "a"):
            return None                                # allow Ctrl+C / Ctrl+A
        return "break"

    def _insert(self, level: str, text: str, link) -> None:
        tag = level if level in LOG_LEVELS else "INFO"
        if level == "SECTION":
            self.text.insert("end", "\n" + text + "\n", ("SECTION",))
        else:
            prefix_tags = (tag, "errlink") if (level in ("ERROR", "FAIL") and self._error_csv) else (tag,)
            self.text.insert("end", f"[{level}] ", prefix_tags)
            self.text.insert("end", text,
                             (tag,) if level in ("ERROR", "FAIL", "OK", "WARNING", "PASS", "SKIP", "INFO") else ())
            links = link if isinstance(link, list) else ([link] if link else [])
            for d in links:                            # one or more cell links (both sides of a partial match)
                self.text.insert("end", "   ")
                lt = f"lnk{self._lnk}"
                self._lnk += 1
                self._links[lt] = d
                self.text.insert("end", f"[open {d['sheet']}!{d['cell']}]", ("link", lt))
                self.text.tag_bind(lt, "<Button-1>", lambda e, dd=d: self._open_link(dd))
                self.text.tag_bind(lt, "<Enter>", lambda e: self.text.config(cursor="hand2"))
                self.text.tag_bind(lt, "<Leave>", lambda e: self.text.config(cursor=""))
            self.text.insert("end", "\n")
        self.text.see("end")

    def _link_token(self, text: str, link: dict) -> None:
        """Insert `text` as a clickable Excel-jump link (accent + underline)."""
        lt = f"lnk{self._lnk}"
        self._lnk += 1
        self._links[lt] = link
        self.text.insert("end", text, ("link", lt))
        self.text.tag_bind(lt, "<Button-1>", lambda e, dd=link: self._open_link(dd))
        self.text.tag_bind(lt, "<Enter>", lambda e: self.text.config(cursor="hand2"))
        self.text.tag_bind(lt, "<Leave>", lambda e: self.text.config(cursor=""))

    def _insert_line(self, level, location, body, link1, link2) -> None:
        """A structured cross-check line: [LEVEL] <clickable cell> <aligned body> [open other-wb]."""
        tag = "WARNING" if level == "WARN" else (level if level in LOG_LEVELS else "INFO")
        prefix_tags = (tag, "errlink") if (level in ("ERROR", "FAIL") and self._error_csv) else (tag,)
        self.text.insert("end", f"[{level}] ", prefix_tags)
        if location:
            cell = location.rstrip()                   # the link is the cell; keep padding plain
            if link1 and cell:
                self._link_token(cell, link1)
            else:
                self.text.insert("end", cell, (tag,))
            self.text.insert("end", location[len(cell):] + " ", (tag,))
        if body:
            self.text.insert("end", body, (tag,))
        if link2:
            self.text.insert("end", "   ")
            self._link_token(f"[open {link2['sheet']}!{link2['cell']}]", link2)
        self.text.insert("end", "\n")
        self.text.see("end")

    def _open_link(self, link: dict) -> None:
        if self._on_status:
            self._on_status(f"opening Excel at {link['sheet']}!{link['cell']} ...")

        def work():
            ok, msg = excel_goto(link.get("path", ""), link["sheet"], link["cell"])
            self.post_status(msg)
        threading.Thread(target=work, daemon=True).start()

    def _open_file(self, path) -> None:
        """Open a file (the error_management.csv) in the OS default app."""
        if not path or not os.path.exists(path):
            self.post_status("error_management.csv not found yet (run a validation first)")
            return
        try:
            os.startfile(path)  # type: ignore[attr-defined]
            self.post_status(f"opened {os.path.basename(path)}")
        except Exception as e:  # noqa: BLE001
            self.post_status(f"could not open {path}: {e}")

    def _drain(self):
        try:
            while True:
                ev = self.q.get_nowait()
                kind = ev[0]
                if kind == "log":
                    self._insert(ev[1], ev[2], ev[3])
                elif kind == "logline":
                    self._insert_line(ev[1], ev[2], ev[3], ev[4], ev[5])
                elif kind == "errlink":
                    self._error_csv = ev[1]
                elif kind == "status" and self._on_status:
                    self._on_status(ev[1])
                elif kind == "busy" and self._on_busy:
                    self._on_busy(ev[1])
                elif kind == "clear":
                    self.text.delete("1.0", "end")
                    self._links.clear()
        except queue.Empty:
            pass
        self.after(60, self._drain)
