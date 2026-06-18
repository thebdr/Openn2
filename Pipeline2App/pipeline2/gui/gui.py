#!/usr/bin/env python3
"""gui.py - Tkinter front-end for the safety-DB pipeline (headless twin: run.py).

An Open2App-style operator window:
  * a toolbar with "Run All" plus one button per generation phase (Staging, I/O Tags,
    DBs, Diagnosis, Hardware, Interfaces); Validation is a left vertical cascade;
  * a colour-coded Log viewer (ERROR/FAIL red, WARNING amber, PASS/OK green,
    section headers bold) - the pipeline runs on a worker thread so the UI
    stays responsive, exactly like Open2App's TiaWorker;
  * clickable log links: a validation "CAUSE&EFFECT MATRIX!F7" (or a hardware
    "row 5") opens the source workbook in Excel AT THAT CELL (tools/excel_goto.ps1);
  * a Configuration tab that edits config_project/project_params.yaml and opens the config CSVs.

Run (from the Pipeline2App root):
      python  launch_gui.py    (shows a console - handy the first time)
      pythonw launch_gui.py    (no console)
(`python pipeline2/gui/gui.py` also works - each submodule bootstraps the app root onto sys.path.)
"""
from __future__ import annotations
import importlib
import json
import os
import queue
import re
import sys
import threading
import traceback
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP_ROOT = os.path.dirname(os.path.dirname(_HERE))   # Pipeline2App (so `pipeline2` resolves
if _APP_ROOT not in sys.path:                         # when a submodule is run directly)
    sys.path.insert(0, _APP_ROOT)

from pipeline2.core import config, staging, validation, outputs, hardware, i18n, error_management
from pipeline2.interfaces import interface_tool
from pipeline2.gui import editor
from pipeline2.gui import project
from pipeline2.gui import gui_common
from pipeline2.gui import phasebar
from pipeline2.gui import theme
from pipeline2.blocks import block_templates
from pipeline2.blocks import block_builders
from pipeline2.blocks import softwareblocks
from pipeline2.blocks import blockshells
from pipeline2.interfaces import verify

APP_NAME = "Pipeline2"
ICON_BASE = os.path.join(config.APP_ROOT, "assets", APP_NAME)  # + .ico / .png

LOG_LEVELS = {"ERROR", "FAIL", "WARNING", "PASS", "SKIP", "OK", "INFO", "SECTION"}

# Configuration tab: (dotted params.yaml key, label, kind). kind: text|int|file|dir|list
PARAM_SPEC = [
    ("project_code",          "Project code",            "text"),
    ("io_list.path",          "I/O List file",           "file"),
    ("io_list.sheet",         "I/O List sheet(s)",       "list"),
    ("io_list.header_row",    "I/O List header row",     "int"),
    ("ce.path",               "Cause&Effect file",       "file"),
    ("ce.matrix_sheet",       "C&E matrix sheet",        "text"),
    ("ce.matrix_header_row",  "C&E matrix header row",   "int"),
    ("ce.matrix_data_row",    "C&E matrix data row",     "int"),
    ("ce.area_header_row",    "AREA header row",         "int"),
    ("ce.area_data_row",      "AREA data row",           "int"),
    ("device_types_db",       "DeviceTypesDatabase",     "file"),
    ("interface_template",    "Interface template",      "file"),
    ("output_dir",            "Output dir",              "dir"),
    ("csv_delimiter",         "CSV delimiter",           "text"),
    ("strike_handling",       "Strikethrough handling",  "text"),
    ("diag_bit_min",          "Diag bit min",            "int"),
    ("diag_bit_max",          "Diag bit max",            "int"),
    ("safety_nets",           "Safety nets (comma sep)", "list"),
    ("areas",                 "Areas (comma sep)",       "list"),
    ("sorter_areas",          "Sorter areas (comma sep)","list"),
]

PHASES = ["Staging", "Validation", "I/O Tags", "DBs", "Diagnosis", "Hardware", "Interfaces"]


# --------------------------------------------------------------------------- #
# Excel navigation                                                            #
# --------------------------------------------------------------------------- #
def _bring_to_front(hwnd: int) -> None:
    """Force a window to the foreground, working around Windows' focus lock by
    briefly attaching to the current foreground thread's input."""
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
    """Open `path` in Excel, select `sheet!cell`, and bring Excel to the front.
    Reuses a running Excel instance (pywin32 COM); falls back to just opening the
    workbook if pywin32 is missing. Runs on a worker thread, so COM is initialised
    here and torn down at the end."""
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
        xl.Goto(ws.Range(cell), True)   # scroll so the cell is top-left
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
# small helpers                                                               #
# --------------------------------------------------------------------------- #
def _abs(path: str) -> str:
    return path if os.path.isabs(path) else os.path.normpath(os.path.join(_HERE, path))


def _get(d: dict, dotted: str):
    cur = d
    for k in dotted.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return cur


def _set(d: dict, dotted: str, value) -> None:
    keys = dotted.split(".")
    cur = d
    for k in keys[:-1]:
        cur = cur.setdefault(k, {})
    cur[keys[-1]] = value


# --------------------------------------------------------------------------- #
# the application                                                             #
# --------------------------------------------------------------------------- #
# The big App class is split across mixins (you cannot split a class across files
# otherwise). These imports come AFTER the constants/helpers above so the mixin
# modules can `from pipeline2.gui.gui import PARAM_SPEC, _abs, ...` without a
# circular-import failure (this module is already bound in sys.modules with those
# names defined by the time the mixins are imported).
from pipeline2.gui._app_actions import ActionsMixin
from pipeline2.gui._app_tabs import TabsMixin


class App(ActionsMixin, TabsMixin):
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_NAME)
        self.root.geometry("1040x700")
        self._set_icon()
        self.q: queue.Queue = queue.Queue()
        self.busy = False
        self._links: dict[str, dict] = {}
        self._lnk = 0
        self._rows = None          # cached staged rows (invalidated on config save)
        self._populated_path = None  # the "Fill I/O List" output copy; staging reads it once set
        self._run_buttons: list[ttk.Button] = []
        self.status = tk.StringVar(value="Ready")
        self._style = ttk.Style(self.root)
        self._dark = tk.BooleanVar(value=False)
        self._large_font = tk.BooleanVar(value=False)   # log viewer font 10 -> 13

        # the canonical config is always config_project/project_params.yaml; File > Open switches to a project
        # for that session (we deliberately do NOT auto-reopen a "last project" on launch).
        self._project_path = config.PARAMS_FILE
        self._cfg_vars: dict[str, tk.StringVar] = {}    # populated by _build_config_tab
        self._lang = self._read_language()
        self.lang_var = tk.StringVar(value=self._lang)
        self.copy_inputs_var = tk.BooleanVar(value=self._read_copy_inputs())

        self._error_csv = None     # current run's error_management.csv ([FAIL] tag links to it)
        self._build_menubar()
        self._build_phasebar()     # the horizontal phase bar + chevron dropdown popups (top)
        self._build_body()         # the Log / Configuration / Files notebook
        self._build_statusbar()
        self._apply_theme()        # colours, tab font, log tags (light by default)
        self._update_title()

        # the [FAIL] tag is a shared "errlink" (underline; keeps the FAIL colour) opening the
        # current error_management.csv; the binding reads self._error_csv live.
        self.log.tag_configure("errlink", underline=True)
        self.log.tag_bind("errlink", "<Button-1>", lambda e: self._open_error_csv())
        self.log.tag_bind("errlink", "<Enter>", lambda e: self.log.config(cursor="hand2"))
        self.log.tag_bind("errlink", "<Leave>", lambda e: self.log.config(cursor=""))

        self.root.after(60, self._drain)
        self._log("INFO", f"{APP_NAME} ready. Output -> {self._out_dir()}", None)
        self._log("INFO", "Click a phase, or 'Run All'. Click an [open ...] link to jump to that Excel cell.", None)

    # ---- project / language state ------------------------------------- #
    def _read_language(self) -> str:
        try:
            return project.load_doc(self._project_path).get("language") or "en"
        except Exception:  # noqa: BLE001
            return "en"

    def _read_copy_inputs(self) -> bool:
        try:
            return bool(project.load_doc(self._project_path).get("copy_inputs_on_save"))
        except Exception:  # noqa: BLE001
            return False

    def _update_title(self):
        if os.path.abspath(self._project_path) == os.path.abspath(config.PARAMS_FILE):
            self.root.title(APP_NAME)
        else:
            self.root.title(f"{APP_NAME} - {project.project_name(self._project_path)}")

    def _build_menubar(self):
        gui_common.build_menubar(self.root, {
            "new": self._proj_new, "open": self._proj_open, "save": self._save_params,
            "save_as": self._proj_save_as, "archive": self._proj_archive,
            "set_language": self._set_language, "toggle_copy_inputs": None,
        }, self.lang_var, self.copy_inputs_var)

    def _build_body(self):
        body = ttk.Frame(self.root)
        body.pack(side="top", fill="both", expand=True)
        self._build_notebook(body)

    # ---- the horizontal phase bar (replaces the old toolbar + left cascade) --- #
    def _build_phasebar(self):
        self._phasebar_holder = ttk.Frame(self.root)
        self._phasebar_holder.pack(side="top", fill="x")
        self._populate_phasebar()

    def _populate_phasebar(self):
        """(Re)build the phase bar - called on launch and on a language/project change to relabel."""
        holder = self._phasebar_holder
        for w in holder.winfo_children():
            w.destroy()
        self._run_buttons[:] = [b for b in self._run_buttons if b.winfo_exists()]
        run, phases = self._phase_spec()
        bar = phasebar.PhaseBar(holder, run, phases, self._run_buttons, padding=(6, 4))
        bar.pack(side="left", fill="x")
        self._phasebar = bar
        # the utility cluster (Open Output / Clear Log / Large font / Dark mode) lives beside the
        # notebook tab selector now - see _build_utilities.

    def _phase_spec(self):
        """The declarative phase spec consumed by phasebar.PhaseBar (labels via i18n; action commands
        wrapped in the worker-thread `_start`; opens call the helpers directly; stubs have command=None)."""
        L = lambda k: i18n.tr(k, self._lang)                       # noqa: E731
        act = lambda fn: (lambda: self._start(fn))                 # noqa: E731  run a worker on the thread
        val = lambda ps: act(lambda: self._phase_validation(set(ps)))   # noqa: E731

        phases = [
            {"label": L("ph_validation"), "run": val({"0A", "1", "2", "3"}), "buttons": [
                {"label": L("pb_validate_iolist"), "kind": "action", "command": val({"0A"})},
                {"label": L("pb_validate_ce"), "kind": "disabled", "command": None},
                {"label": L("pb_xcheck_cem_iol"), "kind": "action", "command": val({"1"})},
                {"label": L("pb_xcheck_iol_cem"), "kind": "action", "command": val({"2"})},
                {"label": L("pb_validate_diag"), "kind": "action", "command": val({"3"})},
                {"label": L("pb_open_errmgmt"), "kind": "open", "command": self._open_errmgmt},
                {"label": L("pb_open_iolist"), "kind": "open", "command": self._open_io_list},
                {"label": L("pb_open_ce"), "kind": "open", "command": self._open_ce},
                {"label": L("pb_open_val_logs"), "kind": "open", "command": self._open_reports},
            ]},
            {"label": L("ph_fill"), "run": act(self._phase_fill), "buttons": [
                {"label": L("pb_fill_iolist"), "kind": "action", "command": act(self._phase_fill)},
                {"label": L("pb_open_iolist"), "kind": "open", "command": self._open_io_list},
                {"label": L("pb_open_fill_config"), "kind": "open",
                 "command": lambda: self._open_input_doc("object_families.csv")},
                {"label": L("pb_open_signal_types"), "kind": "open",
                 "command": lambda: self._open_input_doc("signal_types.csv")},
            ]},
            {"label": L("ph_staging"), "run": act(self._phase_staging), "buttons": [
                {"label": L("pb_stage_iolist"), "kind": "action", "command": act(self._phase_staging)},
                {"label": L("pb_gen_io_database"), "kind": "action", "command": act(self._work_export_central)},
                {"label": L("pb_open_io_database"), "kind": "open", "command": self._open_central},
            ]},
            {"label": L("ph_interfaces"), "run": act(self._phase_interfaces), "buttons": [
                {"label": L("pb_gen_interfaces"), "kind": "action", "command": act(self._phase_interfaces)},
                {"label": L("pb_open_interfaces"), "kind": "open",
                 "command": lambda: self._open_out_folder("interfaces_dir")},
                {"label": L("pb_gen_custom_iface"), "kind": "special", "command": None},   # stub (orange)
            ]},
            {"label": L("ph_signals"), "run": act(lambda: (self._phase_iotags(), self._phase_dbs())), "buttons": [
                {"label": L("pb_gen_io_tags"), "kind": "action", "command": act(self._phase_iotags)},
                {"label": L("pb_gen_data_blocks"), "kind": "action", "command": act(self._phase_dbs)},
                {"label": L("pb_open_io_tags"), "kind": "open",
                 "command": lambda: self._open_out_file("io_tags_dir", "PLCTags.xlsx")},
                {"label": L("pb_open_data_blocks"), "kind": "open",
                 "command": lambda: self._open_out_folder("blocks_import_dir")},
            ]},
            {"label": L("ph_diagnosis"), "run": act(self._phase_diagnosis), "buttons": [
                {"label": L("pb_gen_diag_list"), "kind": "action", "command": act(self._phase_diagnosis)},
                {"label": L("pb_gen_diag_blocks"), "kind": "action", "command": act(self._phase_fill)},
                {"label": L("pb_open_diag_data"), "kind": "open",
                 "command": lambda: self._open_out_folder("diagnosis_dir")},
                {"label": L("pb_open_diag_config"), "kind": "open", "command": self._open_diag_config},
            ]},
            {"label": L("ph_hardware"), "run": act(self._phase_hardware), "buttons": [
                {"label": L("pb_gen_stations"), "kind": "action", "command": act(self._phase_hardware)},
                {"label": L("pb_gen_modules"), "kind": "action", "command": act(self._phase_hardware)},
                {"label": L("pb_open_hardware"), "kind": "open",
                 "command": lambda: self._open_out_folder("hardware_dir")},
            ]},
            {"label": L("ph_software"), "run": act(lambda: (self._work_softwareblocks(), self._work_shells())),
             "buttons": [
                {"label": L("pb_gen_blocks"), "kind": "action", "command": act(self._work_softwareblocks)},
                {"label": L("pb_gen_instances"), "kind": "action", "command": act(self._work_softwareblocks)},
                {"label": L("pb_gen_shells"), "kind": "action", "command": act(self._work_shells)},
                {"label": L("pb_open_shells"), "kind": "open", "command": self._open_shell_xlsm},
            ]},
            {"label": L("ph_reporting"), "run": act(self._work_coverage), "buttons": [
                {"label": L("pb_gen_cov_p2"), "kind": "action", "command": act(self._work_coverage)},
                {"label": L("pb_gen_cov_tia"), "kind": "disabled", "command": None},
                {"label": L("pb_open_reports"), "kind": "open", "command": self._open_reports},
            ]},
        ]
        run = {"label": L("pb_run_pipeline"), "command": act(self._work_run_all)}
        return run, phases

    def _apply_theme(self):
        """Apply the current (light/dark) palette to ttk, the log, and the editor."""
        dark = self._dark.get()
        pal = theme.palette(dark)
        theme.apply_ttk(self._style, pal)
        base = 13 if self._large_font.get() else 10        # log-viewer font size (toolbar toggle)
        self.log.configure(background=pal["log_bg"], foreground=pal["log_fg"],
                           insertbackground=pal["log_fg"], font=("Consolas", base))
        for level, cfg in theme.log_tags(dark).items():
            cfg = dict(cfg)
            if "font" in cfg:                              # keep each tag's relative size + style
                fam, sz, *style = cfg["font"]
                cfg["font"] = (fam, base + (sz - 10), *style)
            self.log.tag_configure(level, **cfg)
        self.log.tag_configure("link", foreground=pal["accent"], underline=True)
        files = getattr(self, "_files", None)
        if files is not None:
            files.apply_theme(pal)

    # ---- widget construction ------------------------------------------- #
    def _set_icon(self):
        """Window/taskbar icon from assets/Pipeline2.ico (preferred) or .png."""
        try:
            if os.path.exists(ICON_BASE + ".ico"):
                self.root.iconbitmap(ICON_BASE + ".ico")
            elif os.path.exists(ICON_BASE + ".png"):
                self._icon = tk.PhotoImage(file=ICON_BASE + ".png")  # keep a ref
                self.root.iconphoto(True, self._icon)
        except Exception:  # noqa: BLE001 - icon is cosmetic
            pass

    def _build_notebook(self, parent=None):
        nb = ttk.Notebook(parent or self.root)
        nb.pack(side="left", fill="both", expand=True, padx=6, pady=(0, 4))
        self._nb = nb

        # --- Log tab ---
        log_tab = ttk.Frame(nb)
        nb.add(log_tab, text="Log")
        self.log = tk.Text(log_tab, wrap="word", font=("Consolas", 10), undo=False)
        ys = ttk.Scrollbar(log_tab, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=ys.set)
        ys.pack(side="right", fill="y")
        self.log.pack(side="left", fill="both", expand=True)
        self.log.bind("<Key>", self._readonly_keys)  # read-only but keep copy/select
        # colours + tags are set in _apply_theme

        # --- Configuration tab ---
        cfg_tab = ttk.Frame(nb, padding=10)
        nb.add(cfg_tab, text="Configuration")
        self._build_config_tab(cfg_tab)

        # --- Files tab (config + outputs editor) ---
        files_tab = ttk.Frame(nb)
        nb.add(files_tab, text="Files")
        self._files_tab = files_tab
        self._build_files_tab(files_tab)

        # the utility cluster sits beside the tab selector (top-right of the notebook tab strip)
        util = ttk.Frame(parent or self.root)
        ttk.Button(util, text="Open Output", command=self._open_output).pack(side="left", padx=2)
        ttk.Button(util, text="Clear Log", command=self._clear_log).pack(side="left", padx=2)
        ttk.Checkbutton(util, text="Large font", variable=self._large_font,
                        command=self._apply_theme).pack(side="left", padx=(8, 0))
        ttk.Checkbutton(util, text="Dark mode", variable=self._dark,
                        command=self._apply_theme).pack(side="left", padx=(8, 0))
        util.place(in_=nb, relx=1.0, x=-8, y=3, anchor="ne")
        util.lift()
        self._util = util

    def _build_statusbar(self):
        bar = ttk.Frame(self.root, padding=(8, 4))
        bar.pack(side="bottom", fill="x")
        self.progress = ttk.Progressbar(bar, mode="indeterminate", length=140)
        self.progress.pack(side="right")
        ttk.Label(bar, textvariable=self.status, anchor="w").pack(side="left", fill="x", expand=True)

    # ---- log rendering (main thread) ----------------------------------- #
    def _readonly_keys(self, event):
        # allow Ctrl+C / Ctrl+A; block everything else so the log is read-only
        if (event.state & 0x4) and event.keysym.lower() in ("c", "a"):
            return None
        return "break"

    def _insert_log(self, level: str, text: str, link):
        tag = level if level in LOG_LEVELS else "INFO"
        if level == "SECTION":
            self.log.insert("end", "\n" + text + "\n", ("SECTION",))
        else:
            prefix_tags = (tag, "errlink") if (level in ("ERROR", "FAIL") and self._error_csv) else (tag,)
            self.log.insert("end", f"[{level}] ", prefix_tags)
            self.log.insert("end", text,
                            (tag,) if level in ("ERROR", "FAIL", "OK", "WARNING", "PASS", "SKIP", "INFO") else ())
            links = link if isinstance(link, list) else ([link] if link else [])
            for d in links:                            # one or more cell links (both sides of a partial match)
                self.log.insert("end", "   ")
                lt = f"lnk{self._lnk}"
                self._lnk += 1
                self._links[lt] = d
                self.log.insert("end", f"[open {d['sheet']}!{d['cell']}]", ("link", lt))
                self.log.tag_bind(lt, "<Button-1>", lambda e, dd=d: self._open_link(dd))
                self.log.tag_bind(lt, "<Enter>", lambda e: self.log.config(cursor="hand2"))
                self.log.tag_bind(lt, "<Leave>", lambda e: self.log.config(cursor=""))
            self.log.insert("end", "\n")
        self.log.see("end")

    def _link_token(self, text: str, link: dict):
        """Insert `text` as a clickable Excel-jump link (accent + underline)."""
        lt = f"lnk{self._lnk}"
        self._lnk += 1
        self._links[lt] = link
        self.log.insert("end", text, ("link", lt))
        self.log.tag_bind(lt, "<Button-1>", lambda e, dd=link: self._open_link(dd))
        self.log.tag_bind(lt, "<Enter>", lambda e: self.log.config(cursor="hand2"))
        self.log.tag_bind(lt, "<Leave>", lambda e: self.log.config(cursor=""))

    def _insert_line(self, level, location, body, link1, link2):
        """A structured cross-check line: [LEVEL] <clickable cell> <aligned body> [open other-wb]."""
        tag = "WARNING" if level == "WARN" else (level if level in LOG_LEVELS else "INFO")
        prefix_tags = (tag, "errlink") if (level in ("ERROR", "FAIL") and self._error_csv) else (tag,)
        self.log.insert("end", f"[{level}] ", prefix_tags)
        if location:
            cell = location.rstrip()                   # the link is the cell; keep padding plain
            if link1 and cell:
                self._link_token(cell, link1)
            else:
                self.log.insert("end", cell, (tag,))
            self.log.insert("end", location[len(cell):] + " ", (tag,))
        if body:
            self.log.insert("end", body, (tag,))
        if link2:
            self.log.insert("end", "   ")
            self._link_token(f"[open {link2['sheet']}!{link2['cell']}]", link2)
        self.log.insert("end", "\n")
        self.log.see("end")

    def _clear_log(self):
        self.log.delete("1.0", "end")
        self._links.clear()

    def _open_link(self, link: dict):
        self.status.set(f"opening Excel at {link['sheet']}!{link['cell']} ...")

        def work():
            ok, msg = excel_goto(link["path"], link["sheet"], link["cell"])
            self.q.put(("status", msg))
        threading.Thread(target=work, daemon=True).start()

    def _open_error_csv(self):
        path = self._error_csv
        if not path or not os.path.exists(path):
            self.status.set("error_management.csv not found yet (run a validation first)")
            return
        try:
            os.startfile(path)  # type: ignore[attr-defined]
            self.status.set(f"opened {os.path.basename(path)}")
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("error_management.csv", str(e))

    # ---- busy / queue drain (main thread) ------------------------------ #
    def _set_busy(self, busy: bool):
        self.busy = busy
        for b in self._run_buttons:
            b.configure(state="disabled" if busy else "normal")
        if busy:
            self.progress.start(12)
        else:
            self.progress.stop()
            self.status.set("Ready")
            files = getattr(self, "_files", None)
            if files is not None:
                files.refresh()  # surface freshly-generated outputs

    def _drain(self):
        try:
            while True:
                ev = self.q.get_nowait()
                kind = ev[0]
                if kind == "log":
                    self._insert_log(ev[1], ev[2], ev[3])
                elif kind == "logline":
                    self._insert_line(ev[1], ev[2], ev[3], ev[4], ev[5])
                elif kind == "errlink":
                    self._error_csv = ev[1]
                elif kind == "busy":
                    self._set_busy(ev[1])
                elif kind == "status":
                    self.status.set(ev[1])
        except queue.Empty:
            pass
        self.root.after(60, self._drain)


def main():
    root = tk.Tk()
    App(root)  # App applies the theme (clam-based, light by default)
    root.mainloop()


if __name__ == "__main__":
    main()
