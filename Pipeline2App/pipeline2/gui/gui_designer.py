#!/usr/bin/env python3
"""gui_designer.py - the slim "I/O List Checker" for electrical designers.

A dedicated, lightweight window that ONLY validates documents before they are shared:
  Staging -> Phase 0A (I/O List standalone) -> Phase 1/2 (cross-check vs Cause&Effect).
It does NOT generate any artifacts (no DBs/IoTags/hardware/interfaces) and never runs the
diagnosis phase (designers leave the diag columns empty).

Features the full tool shares: a folder-based Project Manager (File menu), an EN/IT language
choice, and the colour-coded log viewer (logview.LogView) with clickable Excel cell links.

Run:  python gui_designer.py        (or the packaged IOListChecker.exe)
"""
from __future__ import annotations
import os
import sys
import threading
import traceback
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# bundle dir when frozen (so the icon resolves in a one-file/one-folder .exe), else the source dir
if getattr(sys, "frozen", False):
    _HERE = getattr(sys, "_MEIPASS", None) or os.path.dirname(sys.executable)
else:
    _HERE = os.path.dirname(os.path.abspath(__file__))
_APP_ROOT = os.path.dirname(os.path.dirname(_HERE))   # Pipeline2App (so `pipeline2` resolves
if _APP_ROOT not in sys.path:                         # when a submodule is run directly)
    sys.path.insert(0, _APP_ROOT)

from pipeline2.core import config, staging, validation, i18n, error_management
from pipeline2.gui import theme
from pipeline2.gui import logview
from pipeline2.gui import project
from pipeline2.gui import gui_common

APP_ICON = os.path.join(_HERE, "assets", "Pipeline2")     # + .ico / .png

# the config form, grouped into sections. Each field = (dotted key, i18n label key, kind);
# kind in {file, text, int, list, bool}. Numeric (row) fields are grouped together, and the
# matrix-validation knobs are all included. io_list.sheet / ce.matrix_sheet are regex patterns.
FORM_SECTIONS = [
    ("sec_iolist", [
        ("io_list.path",         "lbl_iolist_file",   "file"),
        ("io_list.sheet",        "lbl_iolist_sheet",  "list"),
        ("io_list.header_row",   "lbl_iolist_header", "int"),
    ]),
    ("sec_ce", [
        ("ce.path",              "lbl_ce_file",       "file"),
        ("ce.matrix_sheet",      "lbl_ce_sheet",      "text"),
    ]),
    ("sec_rows", [
        ("ce.matrix_header_row", "lbl_ce_matrix_header", "int"),
        ("ce.matrix_data_row",   "lbl_ce_matrix_data",   "int"),
        ("ce.area_header_row",   "lbl_area_header",       "int"),
        ("ce.area_data_row",     "lbl_area_data",         "int"),
    ]),
    ("sec_matrix_val", [
        ("areas",                    "lbl_areas",               "list"),
        ("ce_fuzzy_chars",           "lbl_ce_fuzzy",            "int"),
        ("ce_mandatory_words",       "lbl_ce_mandatory",        "list"),
        ("ce_excluded_words",        "lbl_ce_excluded",         "list"),
        ("ce_always_excluded_words", "lbl_ce_always_excluded",  "list"),
        ("ce_full_check",            "lbl_ce_full_check",       "bool"),
        ("ce_full_print",            "lbl_ce_full_print",       "bool"),
    ]),
]
FIELDS = [f for _sec, fs in FORM_SECTIONS for f in fs]      # flat (key, label, kind) list

# the validation cascade: (i18n label key, phase set), top-to-bottom. Run-all = 0A,0B,1,2.
CASCADE_STEPS = [
    ("btn_iolist_validation", {"0A"}),     # I/O List Validation
    ("btn_ce_validation",     {"0B"}),     # C&E Matrix Validation
    ("btn_io_in_ce",          {"2"}),      # I/O presence in C&E
    ("btn_ce_in_io",          {"1"}),      # C&E presence in I/O
]
RUN_ALL_PHASES = {"0A", "0B", "1", "2"}


# --- tiny dotted-dict + form-value helpers (kept local; no gui.py import) --- #
def _get(d, dotted):
    cur = d
    for k in dotted.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return cur


def _set(d, dotted, value):
    cur = d
    keys = dotted.split(".")
    for k in keys[:-1]:
        cur = cur.setdefault(k, {})
    cur[keys[-1]] = value


def _raw_to_str(value, kind):
    if value is None:
        return ""
    if kind == "list" and isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return str(value)


def _str_to_raw(text, kind):
    text = text.strip()
    if kind == "int":
        try:
            return int(text)
        except ValueError:
            return text
    if kind == "list":
        items = [p.strip() for p in text.split(",") if p.strip()]
        from ruamel.yaml.comments import CommentedSeq
        seq = CommentedSeq(items)
        seq.fa.set_flow_style()
        return seq
    return text


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.busy = False
        self._run_buttons: list = []
        self._rows = None
        self._params = None
        self._cfg_vars: dict[str, tk.StringVar] = {}

        # the canonical config is always config_project/project_params.yaml; File > Open/New switches the
        # project for the session (no auto-reopen of a "last project" on launch).
        self._project_path = config.PARAMS_FILE
        self._lang = self._read_language()
        self.lang_var = tk.StringVar(value=self._lang)
        self.copy_inputs_var = tk.BooleanVar(value=self._read_copy_inputs())
        self.status = tk.StringVar(value=i18n.tr("status_ready", self._lang))

        self._set_icon()
        self._style = ttk.Style(self.root)
        theme.apply_ttk(self._style, theme.palette(False))

        self._build_menubar()
        self._build_statusbar()        # creates self.progress (logview's on_busy uses it)
        self._build_body()             # persistent log view (right) + rebuildable left panel
        self._update_title()
        self._reload_form()

    # ---- small readers off the current project doc ---- #
    def _read_language(self) -> str:
        try:
            return (project.load_doc(self._project_path).get("language") or "en")
        except Exception:  # noqa: BLE001
            return "en"

    def _read_copy_inputs(self) -> bool:
        try:
            return bool(project.load_doc(self._project_path).get("copy_inputs_on_save"))
        except Exception:  # noqa: BLE001
            return False

    def _set_icon(self):
        try:
            if os.path.exists(APP_ICON + ".ico"):
                self.root.iconbitmap(APP_ICON + ".ico")
            elif os.path.exists(APP_ICON + ".png"):
                self._icon = tk.PhotoImage(file=APP_ICON + ".png")
                self.root.iconphoto(True, self._icon)
        except Exception:  # noqa: BLE001
            pass

    def _update_title(self):
        if os.path.abspath(self._project_path) == os.path.abspath(config.PARAMS_FILE):
            name = i18n.tr("no_project", self._lang)
        else:
            name = project.project_name(self._project_path)
        self.root.title(f"{i18n.tr('app_title_designer', self._lang)} - {name}")

    # ---- UI construction ---- #
    def _build_menubar(self):
        gui_common.build_menubar(self.root, {
            "new": self._new, "open": self._open, "save": self._save, "save_as": self._save_as,
            "archive": self._archive, "quit": self.root.destroy,
            "set_language": self._set_language, "toggle_copy_inputs": None,
        }, self.lang_var, self.copy_inputs_var)

    def _build_body(self):
        # persistent skeleton: a rebuildable LEFT panel (cascade + form + buttons) and a
        # PERSISTENT log view filling the right (so the log survives language/project rebuilds).
        self._body = ttk.Frame(self.root, padding=6)
        self._body.pack(side="top", fill="both", expand=True)
        self._left_holder = ttk.Frame(self._body)
        self._left_holder.pack(side="left", fill="y")
        ttk.Separator(self._body, orient="vertical").pack(side="left", fill="y", padx=4)
        self.logview = logview.LogView(self._body, on_status=self.status.set, on_busy=self._set_busy)
        self.logview.pack(side="left", fill="both", expand=True)
        self.logview.apply_theme(theme.palette(False), False)
        self._build_left()

    def _build_left(self):
        holder = self._left_holder
        # cascade (fixed, top)
        cascade = gui_common.build_validation_cascade(
            holder, (i18n.tr("btn_run_all", self._lang), RUN_ALL_PHASES),
            [(i18n.tr(key, self._lang), phases) for key, phases in CASCADE_STEPS],
            self._on_run, self._run_buttons)
        cascade.pack(side="top", fill="x")
        ttk.Separator(holder, orient="horizontal").pack(side="top", fill="x", pady=6)
        # action buttons (fixed, bottom)
        btns = ttk.Frame(holder)
        btns.pack(side="bottom", fill="x", pady=(6, 0))
        ttk.Button(btns, text=i18n.tr("btn_save", self._lang), command=self._save).pack(side="left")
        ttk.Button(btns, text=i18n.tr("btn_reload", self._lang), command=self._reload_form).pack(side="left", padx=4)
        ttk.Button(btns, text=i18n.tr("btn_open_config", self._lang), command=self._open_config).pack(side="left", padx=4)
        ttk.Button(btns, text=i18n.tr("btn_clear_log", self._lang), command=self.logview.clear).pack(side="left", padx=4)
        ttk.Button(btns, text=i18n.tr("btn_open_output", self._lang), command=self._open_output).pack(side="left", padx=4)
        # config form (scrollable, fills the middle)
        self._build_form(holder)

    def _build_form(self, holder):
        """A vertically-scrollable, grouped config form. Layout per row: label | browse | widget
        (the browse '...' button comes BEFORE the entry)."""
        canvas = tk.Canvas(holder, width=470, highlightthickness=0,
                           background=theme.palette(False)["bg"])
        vs = ttk.Scrollbar(holder, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vs.set)
        vs.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        frm = ttk.Frame(canvas, padding=(2, 2))
        win = canvas.create_window((0, 0), window=frm, anchor="nw")
        frm.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win, width=e.width))
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _wheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        def _wheel(e):
            canvas.yview_scroll(int(-e.delta / 120), "units")

        self._cfg_vars.clear()
        r = 0
        for sec_key, fields in FORM_SECTIONS:
            ttk.Label(frm, text=i18n.tr(sec_key, self._lang), font=("Segoe UI", 9, "bold")).grid(
                row=r, column=0, columnspan=3, sticky="w", pady=(8, 2))
            r += 1
            for key, label_key, kind in fields:
                ttk.Label(frm, text=i18n.tr(label_key, self._lang)).grid(
                    row=r, column=0, sticky="w", padx=(2, 8), pady=1)
                if kind == "bool":
                    var = tk.BooleanVar()
                    ttk.Checkbutton(frm, variable=var).grid(row=r, column=2, sticky="w", pady=1)
                else:
                    var = tk.StringVar()
                    if kind == "file":
                        ttk.Button(frm, text="...", width=3,
                                   command=lambda v=var: self._browse_file(v)).grid(row=r, column=1, padx=(0, 4))
                    ttk.Entry(frm, textvariable=var, width=46).grid(row=r, column=2, sticky="we", pady=1)
                self._cfg_vars[key] = var
                r += 1
        frm.columnconfigure(2, weight=1)

    def _build_statusbar(self):
        bar = ttk.Frame(self.root)
        bar.pack(side="bottom", fill="x")
        self.progress = ttk.Progressbar(bar, mode="indeterminate", length=120)
        self.progress.pack(side="right", padx=6, pady=2)
        ttk.Label(bar, textvariable=self.status, anchor="w").pack(side="left", fill="x", expand=True, padx=8)

    def _rebuild_left(self):
        """Rebuild only the left panel (cascade + form + buttons) on a language/project change;
        the log view persists."""
        self._run_buttons.clear()
        for w in self._left_holder.winfo_children():
            w.destroy()
        self._build_left()
        self._reload_form()

    # ---- config form <-> project doc ---- #
    def _reload_form(self):
        try:
            doc = project.load_doc(self._project_path)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("project.yaml", str(e))
            return
        for key, _label, kind in FIELDS:
            if kind == "bool":
                self._cfg_vars[key].set(bool(_get(doc, key)))
            else:
                self._cfg_vars[key].set(_raw_to_str(_get(doc, key), kind))
        self.copy_inputs_var.set(bool(doc.get("copy_inputs_on_save")))
        self._rows = None
        self._params = None

    def _collect_doc(self):
        doc = project.load_doc(self._project_path)
        for key, _label, kind in FIELDS:
            if kind == "bool":
                _set(doc, key, bool(self._cfg_vars[key].get()))
            else:
                _set(doc, key, _str_to_raw(self._cfg_vars[key].get(), kind))
        doc["copy_inputs_on_save"] = bool(self.copy_inputs_var.get())
        doc["language"] = self._lang
        return doc

    # ---- project manager actions ---- #
    def _new(self):
        base = config.PROJECTS_DIR
        os.makedirs(base, exist_ok=True)
        folder = gui_common.ask_project_name(self.root, base, self._lang)
        if not folder:
            return
        self._project_path = project.new_project(folder)
        self._after_project_change(i18n.tr("project_opened", self._lang, name=project.project_name(self._project_path)))

    def _open(self):
        folder = filedialog.askdirectory(title=i18n.tr("menu_open", self._lang))
        if not folder:
            return
        try:
            self._project_path = project.open_project(folder)
        except FileNotFoundError:
            messagebox.showerror(i18n.tr("menu_open", self._lang), f"{project.PROJECT_FILE} not found in:\n{folder}")
            return
        self._after_project_change(i18n.tr("project_opened", self._lang, name=project.project_name(self._project_path)))

    def _save(self):
        try:
            doc = self._collect_doc()
            project.save_project(doc, self._project_path, copy_inputs=self.copy_inputs_var.get())
        except Exception as e:  # noqa: BLE001
            messagebox.showerror(i18n.tr("menu_save", self._lang), str(e))
            return
        self._rows = self._params = None
        self._reload_form()                      # reflect any copy-inputs path rewrite
        self.status.set(i18n.tr("project_saved", self._lang, name=project.project_name(self._project_path)))

    def _save_as(self):
        base = config.PROJECTS_DIR
        os.makedirs(base, exist_ok=True)
        folder = gui_common.ask_project_name(self.root, base, self._lang,
                                             title=i18n.tr("menu_save_as", self._lang))
        if not folder:
            return
        try:
            self._project_path = project.save_project_as(self._collect_doc(), folder,
                                                         copy_inputs=self.copy_inputs_var.get())
        except Exception as e:  # noqa: BLE001
            messagebox.showerror(i18n.tr("menu_save_as", self._lang), str(e))
            return
        self._after_project_change(i18n.tr("project_saved", self._lang, name=project.project_name(self._project_path)))

    def _archive(self):
        res = gui_common.ask_archive(self.root, project.project_name(self._project_path), self._lang)
        if not res:
            return
        try:
            zpath = project.archive_project(self._project_path, res["name"], res["add_datetime"])
        except Exception as e:  # noqa: BLE001
            messagebox.showerror(i18n.tr("menu_archive", self._lang), str(e))
            return
        self.status.set(i18n.tr("archive_done", self._lang, path=zpath))

    def _after_project_change(self, status_msg):
        self._lang = self._read_language()
        self.lang_var.set(self._lang)
        self._update_title()
        self._build_menubar()
        self._rebuild_left()
        self.status.set(status_msg)

    def _set_language(self):
        self._lang = self.lang_var.get()
        self._update_title()
        self._build_menubar()
        self._rebuild_left()
        self.status.set(i18n.tr("status_ready", self._lang))

    # ---- browse / open ---- #
    def _browse_file(self, var):
        p = filedialog.askopenfilename(title="Select file",
                                       filetypes=[("Excel", "*.xlsx *.xlsm"), ("All", "*.*")])
        if p:
            var.set(os.path.normpath(p))

    def _open_config(self):
        """Open the current project's project.yaml in the OS default editor."""
        try:
            os.startfile(self._project_path)  # type: ignore[attr-defined]
        except Exception as e:  # noqa: BLE001
            messagebox.showerror(i18n.tr("btn_open_config", self._lang), str(e))

    def _open_output(self):
        try:
            out = config.output_root(config.load_params(self._project_path))
        except Exception:  # noqa: BLE001
            out = config.OUTPUT_ROOT
        os.makedirs(out, exist_ok=True)
        try:
            os.startfile(out)  # type: ignore[attr-defined]
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Output", str(e))

    # ---- running validation ---- #
    def _set_busy(self, busy: bool):
        self.busy = busy
        for b in self._run_buttons:
            b.configure(state="disabled" if busy else "normal")
        if busy:
            self.progress.start(12)
        else:
            self.progress.stop()

    def _on_run(self, phase_set):
        if self.busy:
            return
        self.logview.post_busy(True)
        threading.Thread(target=self._guard(lambda: self._work_validate(set(phase_set))), daemon=True).start()

    def _guard(self, target):
        def wrapped():
            try:
                target()
            except Exception as e:  # noqa: BLE001
                self.logview.log("ERROR", f"aborted: {e}")
                self.logview.log("INFO", traceback.format_exc().strip().splitlines()[-1])
            finally:
                self.logview.post_busy(False)
        return wrapped

    def _work_validate(self, phase_set):
        self.logview.post_status(i18n.tr("status_running", self._lang, phase=",".join(sorted(phase_set))))
        params = config.load_params(self._project_path)
        rows = []
        if phase_set & {"1", "2", "3"}:
            rows = self._ensure_rows(params)
        out_dir = config.output_root(params)
        os.makedirs(out_dir, exist_ok=True)
        log = validation.validate(params, rows, phases=phase_set, lang=self._lang, out_dir=out_dir)
        passed, failed, warned = validation.write_log(log, out_dir)
        skipped = sum(1 for e in log if e.level == "SKIP")
        ce_path = (params.get("ce") or {}).get("path", "")
        self.logview.set_error_link(os.path.join(config.USER_INPUT, error_management.CSV_NAME))   # [FAIL] -> registry
        gui_common.render_validation_log(self.logview.section, self.logview.log_line, log,
                                         full_print=True, ce_path=ce_path)
        self.logview.log("OK" if failed == 0 else "WARNING",
                         i18n.tr("summary", self._lang, passed=passed, failed=failed,
                                 warned=warned, skipped=skipped))

    def _ensure_rows(self, params):
        if self._rows is None:
            types = config.load_signal_types()
            self._rows, warns = staging.load_io_list(params, types)
            for w in warns:
                self.logview.log("INFO", w)
        return self._rows


def main():
    root = tk.Tk()
    root.geometry("1040x720")
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
