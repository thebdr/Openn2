#!/usr/bin/env python3
"""gui.py - Tkinter front-end for the safety-DB pipeline (headless twin: run.py).

An Openn2-style operator window:
  * a toolbar with "Run All" plus one button per phase (Staging, Validation,
    I/O Tags, DBs, Diagnosis, Hardware, Interfaces);
  * a colour-coded Log viewer (ERROR/FAIL red, WARNING amber, PASS/OK green,
    section headers bold) - the pipeline runs on a worker thread so the UI
    stays responsive, exactly like Openn2's TiaWorker;
  * clickable log links: a validation "CAUSE&EFFECT MATRIX!F7" (or a hardware
    "row 5") opens the source workbook in Excel AT THAT CELL (tools/excel_goto.ps1);
  * a Configuration tab that edits config/params.json and opens the config CSVs.

Run:  python gui.py        (shows a console - handy the first time)
      pythonw gui.py       (no console)
Always launch THIS copy under C:\\Source\\Repos\\Openn2\\... (a sibling clone exists).
"""
from __future__ import annotations
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
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from safetydb import config, staging, validation, outputs, hardware
import interface_tool
import editor
import theme
import block_templates

APP_NAME = "Pipeline2"
ICON_BASE = os.path.join(_HERE, "assets", APP_NAME)  # + .ico / .png

LOG_LEVELS = {"ERROR", "FAIL", "WARNING", "PASS", "OK", "INFO", "SECTION"}

# Configuration tab: (dotted params.json key, label, kind). kind: text|int|file|dir|list
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


def _params_file() -> str:
    return os.path.join(config.CONFIG_DIR, "params.json")


# --------------------------------------------------------------------------- #
# the application                                                             #
# --------------------------------------------------------------------------- #
class App:
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
        self._run_buttons: list[ttk.Button] = []
        self.status = tk.StringVar(value="Ready")
        self._style = ttk.Style(self.root)
        self._dark = tk.BooleanVar(value=False)

        self._build_toolbar()
        self._build_notebook()
        self._build_statusbar()
        self._apply_theme()        # colours, tab font, log tags (light by default)

        self.root.after(60, self._drain)
        self._log("INFO", f"{APP_NAME} ready. Output -> {self._out_dir()}", None)
        self._log("INFO", "Click a phase, or 'Run All'. Click an [open ...] link to jump to that Excel cell.", None)

    def _apply_theme(self):
        """Apply the current (light/dark) palette to ttk, the log, and the editor."""
        dark = self._dark.get()
        pal = theme.palette(dark)
        theme.apply_ttk(self._style, pal)
        self.log.configure(background=pal["log_bg"], foreground=pal["log_fg"],
                           insertbackground=pal["log_fg"])
        for level, cfg in theme.log_tags(dark).items():
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

    def _build_toolbar(self):
        bar = ttk.Frame(self.root, padding=(8, 6))
        bar.pack(side="top", fill="x")

        run_all = ttk.Button(bar, text="Run All", command=self._on_run_all)
        run_all.pack(side="left")
        self._run_buttons.append(run_all)
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=8)

        for name in PHASES:
            b = ttk.Button(bar, text=name, width=10, command=lambda n=name: self._on_run_phase(n))
            b.pack(side="left", padx=2)
            self._run_buttons.append(b)

        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Button(bar, text="Open Output", command=self._open_output).pack(side="left", padx=2)
        ttk.Button(bar, text="Clear Log", command=self._clear_log).pack(side="left", padx=2)

        ttk.Checkbutton(bar, text="Dark mode", variable=self._dark,
                        command=self._apply_theme).pack(side="right")

    def _build_notebook(self):
        nb = ttk.Notebook(self.root)
        nb.pack(side="top", fill="both", expand=True, padx=6, pady=(0, 4))
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

    def _build_files_tab(self, parent):
        """Spreadsheet/CSV/text editor over the config and output files."""
        roots = [("config", config.CONFIG_DIR)]
        try:
            dtd = config.load_params().get("device_types_db")
            if dtd and os.path.isdir(os.path.dirname(dtd)):
                roots.append(("HardwareConfig", os.path.dirname(dtd)))
        except Exception:  # noqa: BLE001
            pass
        roots.append(("Output", self._out_dir()))
        self._files = editor.FileBrowser(parent, roots, on_status=self.status.set)
        self._files.pack(fill="both", expand=True)

    def _build_config_tab(self, parent):
        ttk.Label(parent, text="config/params.json", font=("Segoe UI", 10, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 6))
        self._cfg_vars: dict[str, tk.StringVar] = {}
        try:
            with open(_params_file(), encoding="utf-8") as f:
                raw = json.load(f)
        except Exception as e:  # noqa: BLE001
            raw = {}
            messagebox.showerror("params.json", f"could not read params.json:\n{e}")

        for i, (key, label, kind) in enumerate(PARAM_SPEC, start=1):
            ttk.Label(parent, text=label).grid(row=i, column=0, sticky="w", padx=(0, 8), pady=1)
            var = tk.StringVar(value=self._raw_to_str(_get(raw, key), kind))
            self._cfg_vars[key] = var
            entry = ttk.Entry(parent, textvariable=var, width=72)
            entry.grid(row=i, column=1, sticky="we", pady=1)
            if kind == "file":
                ttk.Button(parent, text="...", width=3,
                           command=lambda v=var: self._browse_file(v)).grid(row=i, column=2, padx=(4, 0))
            elif kind == "dir":
                ttk.Button(parent, text="...", width=3,
                           command=lambda v=var: self._browse_dir(v)).grid(row=i, column=2, padx=(4, 0))
        parent.columnconfigure(1, weight=1)

        btns = ttk.Frame(parent)
        btns.grid(row=len(PARAM_SPEC) + 1, column=0, columnspan=3, sticky="w", pady=(12, 0))
        ttk.Button(btns, text="Save params.json", command=self._save_params).pack(side="left")
        ttk.Button(btns, text="Reload", command=self._reload_params).pack(side="left", padx=6)
        ttk.Separator(btns, orient="vertical").pack(side="left", fill="y", padx=10)
        ttk.Button(btns, text="Open signal_types.csv",
                   command=lambda: self._open_path(os.path.join(config.CONFIG_DIR, "signal_types.csv"))).pack(side="left", padx=2)
        ttk.Button(btns, text="Open column_map.csv",
                   command=lambda: self._open_path(os.path.join(config.CONFIG_DIR, "column_map.csv"))).pack(side="left", padx=2)
        ttk.Button(btns, text="Open DeviceTypesDatabase.csv",
                   command=self._open_dtd).pack(side="left", padx=2)

        # --- Block templates (tooling) ---
        blk = ttk.LabelFrame(parent, text="Block templates", padding=8)
        blk.grid(row=len(PARAM_SPEC) + 2, column=0, columnspan=3, sticky="we", pady=(14, 0))
        ttk.Label(blk, justify="left", wraplength=640,
                  text="Scan the TIA Software Block templates for !!key$$ placeholders into "
                       "block_templates.json, bind each key, and export the staged Central "
                       "Database (CSV) to inspect / author bindings.").grid(
            row=0, column=0, columnspan=4, sticky="w", pady=(0, 6))
        b_scan = ttk.Button(blk, text="Scan templates → block_templates.json",
                            command=lambda: self._start(self._work_scan_templates))
        b_scan.grid(row=1, column=0, sticky="w", padx=(0, 6), pady=2)
        ttk.Button(blk, text="Edit block_templates.json",
                   command=lambda: self._open_in_files(os.path.join(config.CONFIG_DIR, "block_templates.json"))
                   ).grid(row=1, column=1, sticky="w", padx=6, pady=2)
        b_central = ttk.Button(blk, text="Export Central Database (CSV)",
                               command=lambda: self._start(self._work_export_central))
        b_central.grid(row=1, column=2, sticky="w", padx=6, pady=2)
        ttk.Button(blk, text="Open Central Database",
                   command=self._open_central).grid(row=1, column=3, sticky="w", padx=6, pady=2)
        self._run_buttons.extend([b_scan, b_central])  # greyed while any run is in flight

    def _open_in_files(self, path: str):
        """Open a file in the Files tab editor (switch to it); else open externally."""
        files = getattr(self, "_files", None)
        if files is not None and os.path.exists(path):
            self._nb.select(self._files_tab)
            files.editor.open(path)
        else:
            self._open_path(path)

    def _open_central(self):
        path = os.path.join(self._out_dir(), "CentralDatabase.csv")
        if os.path.exists(path):
            self._open_in_files(path)
        else:
            self.status.set("CentralDatabase.csv not found - run 'Export Central Database' first")

    def _work_scan_templates(self):
        self._section("BLOCK TEMPLATES  (scan !!key$$ -> config/block_templates.json)")
        s = block_templates.build_templates_json()
        self._log("OK", f"+{s['added_templates']} template(s), +{s['added_keys']} new key(s), "
                         f"{s['kept_keys']} kept binding(s)  ->  config/block_templates.json")
        for m in s["missing"]:
            self._log("INFO", f"  key no longer in template (kept): {m}")
        self._stat("block_templates.json updated")

    def _work_export_central(self):
        self._section("CENTRAL DATABASE  (staged rows -> Output/CentralDatabase.csv)")
        self._stat("exporting Central Database ...")
        path = block_templates.dump_staged()
        self._log("OK", f"{os.path.basename(path)} written  ->  {path}")
        self._stat("CentralDatabase.csv exported")

    def _build_statusbar(self):
        bar = ttk.Frame(self.root, padding=(8, 4))
        bar.pack(side="bottom", fill="x")
        self.progress = ttk.Progressbar(bar, mode="indeterminate", length=140)
        self.progress.pack(side="right")
        ttk.Label(bar, textvariable=self.status, anchor="w").pack(side="left", fill="x", expand=True)

    # ---- config-tab helpers -------------------------------------------- #
    @staticmethod
    def _raw_to_str(value, kind) -> str:
        if value is None:
            return ""
        if kind == "list" and isinstance(value, list):
            return ", ".join(str(v) for v in value)
        return str(value)

    @staticmethod
    def _str_to_raw(text: str, kind):
        text = text.strip()
        if kind == "int":
            try:
                return int(text)
            except ValueError:
                return text  # leave as-is; let the loader complain
        if kind == "list":
            return [p.strip() for p in text.split(",") if p.strip()]
        return text

    def _browse_file(self, var: tk.StringVar):
        p = filedialog.askopenfilename(title="Select file")
        if p:
            var.set(os.path.normpath(p))

    def _browse_dir(self, var: tk.StringVar):
        p = filedialog.askdirectory(title="Select folder")
        if p:
            var.set(os.path.normpath(p))

    def _save_params(self):
        try:
            with open(_params_file(), encoding="utf-8") as f:
                raw = json.load(f)
        except Exception:  # noqa: BLE001
            raw = {}
        for key, _label, kind in PARAM_SPEC:
            _set(raw, key, self._str_to_raw(self._cfg_vars[key].get(), kind))
        try:
            with open(_params_file(), "w", encoding="utf-8") as f:
                json.dump(raw, f, indent=2)
                f.write("\n")
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Save failed", str(e))
            return
        self._rows = None  # config changed -> re-stage next run
        self._log("OK", "params.json saved (staged rows invalidated).", None)
        self.status.set("params.json saved")

    def _reload_params(self):
        try:
            with open(_params_file(), encoding="utf-8") as f:
                raw = json.load(f)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("params.json", str(e))
            return
        for key, _label, kind in PARAM_SPEC:
            self._cfg_vars[key].set(self._raw_to_str(_get(raw, key), kind))
        self.status.set("params.json reloaded")

    def _open_dtd(self):
        try:
            params = config.load_params()
            self._open_path(params["device_types_db"])
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("DeviceTypesDatabase", str(e))

    def _open_path(self, path: str):
        if os.path.exists(path):
            try:
                os.startfile(path)  # type: ignore[attr-defined]
            except Exception as e:  # noqa: BLE001
                messagebox.showerror("Open", str(e))
        else:
            messagebox.showwarning("Open", f"not found:\n{path}")

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
            self.log.insert("end", f"[{level}] ", (tag,))
            self.log.insert("end", text, (tag,) if level in ("ERROR", "FAIL", "OK", "WARNING") else ())
            if link:
                self.log.insert("end", "   ")
                lt = f"lnk{self._lnk}"
                self._lnk += 1
                self._links[lt] = link
                self.log.insert("end", f"[open {link['sheet']}!{link['cell']}]", ("link", lt))
                self.log.tag_bind(lt, "<Button-1>", lambda e, d=link: self._open_link(d))
                self.log.tag_bind(lt, "<Enter>", lambda e: self.log.config(cursor="hand2"))
                self.log.tag_bind(lt, "<Leave>", lambda e: self.log.config(cursor=""))
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
                elif kind == "busy":
                    self._set_busy(ev[1])
                elif kind == "status":
                    self.status.set(ev[1])
        except queue.Empty:
            pass
        self.root.after(60, self._drain)

    # ---- run actions (spawn worker) ------------------------------------ #
    def _on_run_all(self):
        self._start(self._work_run_all)

    def _on_run_phase(self, name: str):
        self._start(lambda: self._work_phase(name))

    def _start(self, target):
        if self.busy:
            return
        self.q.put(("busy", True))
        threading.Thread(target=self._guard(target), daemon=True).start()

    def _guard(self, target):
        def wrapped():
            try:
                target()
            except Exception as e:  # noqa: BLE001
                self._log("ERROR", f"aborted: {e}", None)
                self._log("INFO", traceback.format_exc().strip().splitlines()[-1], None)
            finally:
                self.q.put(("busy", False))
        return wrapped

    # ---- worker-thread emit helpers ------------------------------------ #
    def _log(self, level, text, link=None):
        self.q.put(("log", level, text, link))

    def _section(self, title):
        self.q.put(("log", "SECTION", title, None))

    def _stat(self, text):
        self.q.put(("status", text))

    # ---- worker-thread pipeline ---------------------------------------- #
    def _out_dir(self) -> str:
        try:
            params = getattr(self, "_params", None) or config.load_params()
            return _abs(params.get("output_dir", "Output"))
        except Exception:  # noqa: BLE001
            return _abs("Output")

    def _load_models(self):
        self._params = config.load_params()
        self._types = config.load_signal_types()
        self._dtd = config.load_device_types_db(self._params)

    def _ensure_staged(self):
        self._load_models()
        if self._rows is None:
            io_path = self._params["io_list"]["path"]
            if not os.path.exists(io_path):
                raise FileNotFoundError(f"I/O List not found: {io_path}")
            self._stat("staging - reading I/O List ...")
            self._rows, self._warns = staging.load_io_list(self._params, self._types)

    def _staging_link(self, warning: str):
        cm = re.search(r"column ([A-Z]+)", warning)
        if not cm:
            return None
        io = self._params["io_list"]
        sm = re.search(r"IoList\[([^\]]+)\]", warning)  # the sheet the warning is about
        sheets = config.as_sheet_list(io.get("sheet"))
        sheet = sm.group(1) if sm else (sheets[0] if sheets else "")
        return {"path": io["path"], "sheet": sheet, "cell": f"{cm.group(1)}{io['header_row']}"}

    def _phase_staging(self):
        self._section("STAGING  (reading the I/O List)")
        self._ensure_staged()
        self._log("OK", f"{len(self._rows)} row(s) loaded")
        for w in self._warns:
            is_warn = ("header" in w and "!=" in w)
            self._log("WARNING" if is_warn else "INFO", w, self._staging_link(w) if is_warn else None)

    def _phase_validation(self):
        self._section("VALIDATION  (C&E / AREA vs I/O List)")
        self._ensure_staged()
        ce = self._params["ce"]
        if not os.path.exists(ce["path"]):
            self._log("WARNING", f"C&E document not found - skipped: {ce['path']}")
            return
        self._stat("validating C&E / AREA ...")
        log = validation.validate(self._params, self._rows)
        passed, failed = validation.write_log(log, self._out_dir())
        self._log("OK" if failed == 0 else "WARNING",
                  f"{passed} passed, {failed} failed  ->  Output/validation_log.txt")
        for e in log:
            link = None
            if "!" in e.location:
                sheet, cell = e.location.split("!", 1)
                link = {"path": ce["path"], "sheet": sheet, "cell": cell}
            if e.level == "FAIL":
                self._log("FAIL", f"{e.location}: {e.message}", link)

    def _phase_iotags(self):
        self._section("I/O TAGS")
        self._ensure_staged()
        tables = outputs.build_io_tags(self._rows)
        n = outputs.write_io_tags(tables, self._out_dir())
        self._log("OK", f"{n} tag(s) across {len(tables)} table(s)  ->  Output/IoTags/PLCTags.xlsx")

    def _phase_dbs(self):
        self._section("DATA BLOCKS")
        self._ensure_staged()
        dbs = outputs.build_dbs(self._rows, self._types)
        n = outputs.write_dbs(dbs, self._out_dir())
        self._log("OK", f"{n} DB(s)  ->  Output/DBs")
        for name, db in sorted(dbs.items()):
            kind = "safe" if db["kind"] == "safe_db" else "std"
            self._log("INFO", f"  {name}  ({kind}, {len(db['members'])} member(s))")

    def _phase_diagnosis(self):
        self._section("DIAGNOSIS  (List_IO)")
        self._ensure_staged()
        diag = outputs.build_diagnosis_list_io(self._rows)
        n = outputs.write_diagnosis_list_io(diag, self._out_dir())
        self._log("OK", f"{n} row(s)  ->  Output/Diagnosis/List_IO.csv")

    def _phase_hardware(self):
        self._section("HARDWARE  (Stations / Modules, format 2)")
        self._ensure_staged()
        stations, modules, messages = hardware.extract(self._rows, self._dtd)
        nst = hardware.write_stations(stations, self._out_dir())
        nmod = hardware.write_modules(modules, self._out_dir())
        self._log("OK", f"{nst} station(s), {nmod} module(s)  ->  Output/Hardware")
        io = self._params["io_list"]
        sheets = config.as_sheet_list(io.get("sheet"))
        default_sheet = sheets[0] if sheets else ""
        for level, text in messages:
            sm = re.search(r"\[([^\]]+)\] row (\d+)", text)   # "[sheet] row N ..."
            rm = re.search(r"row (\d+)", text)
            if sm:
                sheet, n = sm.group(1), sm.group(2)
            elif rm:
                sheet, n = default_sheet, rm.group(1)
            else:
                sheet = n = None
            link = {"path": io["path"], "sheet": sheet, "cell": f"A{n}"} if n else None
            self._log(level, text, link)

    def _phase_interfaces(self):
        self._section("INTERFACES  (IOC rows)")
        self._load_models()
        io = self._params["io_list"]
        tpl = _abs(self._params.get("interface_template", "Templates/TEMPLATE_INTERFACES_v0.0.xlsx"))
        if not os.path.exists(tpl):
            self._log("WARNING", f"interface template not found - skipped: {tpl}")
            return
        self._stat("generating interfaces ...")
        n = interface_tool.generate(io["path"], io["sheet"], io["header_row"],
                                    os.path.join(self._out_dir(), "Interfaces"), tpl)
        self._log("OK", f"{n} interface file(s) created (existing preserved)  ->  Output/Interfaces")

    _PHASE_FN = {
        "Staging": "_phase_staging", "Validation": "_phase_validation",
        "I/O Tags": "_phase_iotags", "DBs": "_phase_dbs", "Diagnosis": "_phase_diagnosis",
        "Hardware": "_phase_hardware", "Interfaces": "_phase_interfaces",
    }

    def _work_phase(self, name: str):
        getattr(self, self._PHASE_FN[name])()
        self._stat(f"{name} done")

    def _work_run_all(self):
        self._rows = None  # always start from a fresh stage
        for name in PHASES:
            getattr(self, self._PHASE_FN[name])()
        self._section("DONE")
        self._log("OK", f"pipeline complete  ->  {self._out_dir()}")
        self._stat("Run All done")

    # ---- misc ----------------------------------------------------------- #
    def _open_output(self):
        out = self._out_dir()
        os.makedirs(out, exist_ok=True)
        self._open_path(out)


def main():
    root = tk.Tk()
    App(root)  # App applies the theme (clam-based, light by default)
    root.mainloop()


if __name__ == "__main__":
    main()
