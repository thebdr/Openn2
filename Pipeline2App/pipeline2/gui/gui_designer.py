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
from pipeline2.gui import phasebar

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

# the only knobs the designer needs inline (beside the Documents Validation button): the two source
# files + the two matrix-validation toggles. Everything else stays at its project.yaml default.
INLINE_FIELDS = [
    ("io_list.path",  "lbl_iolist_file",   "file"),
    ("ce.path",       "lbl_ce_file",       "file"),
    ("ce_full_check", "lbl_ce_full_check", "bool"),
    ("ce_full_print", "lbl_ce_full_print", "bool"),
]


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
        # the designer ships with its OWN validation-focused base (not the main project_params.yaml);
        # File > Open/New switches the project for the session (no auto-reopen of a "last project").
        self._project_path = config.DESIGNER_PARAMS_FILE
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
        if os.path.abspath(self._project_path) == os.path.abspath(config.DESIGNER_PARAMS_FILE):
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
        # a rebuildable TOP bar (the Documents Validation phase button + the few inline controls) and a
        # PERSISTENT log view filling the rest (so the log survives language/project rebuilds).
        self._top_holder = ttk.Frame(self.root, padding=(6, 4))
        self._top_holder.pack(side="top", fill="x")
        self.logview = logview.LogView(self.root, on_status=self.status.set, on_busy=self._set_busy)
        self.logview.pack(side="top", fill="both", expand=True, padx=6, pady=(0, 4))
        self.logview.apply_theme(theme.palette(False), False)
        self._build_topbar()

    def _phase_spec(self):
        """The single 'Documents Validation' phase for the designer (no other generation phases)."""
        L = lambda k: i18n.tr(k, self._lang)                       # noqa: E731
        val = lambda ps: (lambda: self._on_run(set(ps)))           # noqa: E731
        phase = {"label": L("ph_validation"), "run": val({"0A", "1", "2"}), "buttons": [
            {"label": L("pb_validate_iolist"), "kind": "action", "command": val({"0A"})},
            {"label": L("pb_validate_ce"), "kind": "disabled", "command": None},
            {"label": L("pb_xcheck_cem_iol"), "kind": "action", "command": val({"1"})},
            {"label": L("pb_xcheck_iol_cem"), "kind": "action", "command": val({"2"})},
            {"label": L("pb_open_errmgmt"), "kind": "open",
             "command": lambda: self._open_file(os.path.join(config.USER_INPUT, error_management.CSV_NAME))},
            {"label": L("pb_open_iolist"), "kind": "open",
             "command": lambda: self._open_file(self._doc_path("io_list"))},
            {"label": L("pb_open_ce"), "kind": "open",
             "command": lambda: self._open_file(self._doc_path("ce"))},
            {"label": L("pb_open_val_logs"), "kind": "open", "command": self._open_reports},
        ]}
        return None, [phase]

    def _doc_path(self, key) -> str:
        try:
            return (config.load_params(self._project_path).get(key) or {}).get("path", "")
        except Exception:  # noqa: BLE001
            return ""

    def _open_file(self, path: str):
        if path and os.path.exists(path):
            try:
                os.startfile(path)  # type: ignore[attr-defined]
            except Exception as e:  # noqa: BLE001
                messagebox.showerror("Open", str(e))
        else:
            self.status.set(f"not found: {path}")

    def _open_reports(self):
        try:
            out = config.output_root(config.load_params(self._project_path))
        except Exception:  # noqa: BLE001
            out = config.OUTPUT_ROOT
        folder = os.path.dirname(config.out_path(out, "validation_report"))
        os.makedirs(folder, exist_ok=True)
        self._open_file(folder)

    def _build_topbar(self):
        holder = self._top_holder
        for w in holder.winfo_children():
            w.destroy()
        self._run_buttons.clear()
        # the single-phase bar (Documents Validation) on the left
        run, phases = self._phase_spec()
        bar = phasebar.PhaseBar(holder, run, phases, self._run_buttons, padding=(2, 4))
        bar.pack(side="left", fill="y")
        self._phasebar = bar
        ttk.Button(holder, text=i18n.tr("btn_clear_log", self._lang),
                   command=self.logview.clear).pack(side="right", padx=8)
        # the few inline controls on the RIGHT of the Documents Validation button: the two source-file
        # pickers + the matrix-validation toggles (everything else stays at its project.yaml default).
        self._cfg_vars.clear()
        ctrls = ttk.Frame(holder, padding=(14, 2))
        ctrls.pack(side="left", fill="x", expand=True)
        r = 0
        for key, label_key, kind in INLINE_FIELDS:
            if kind != "file":
                continue
            ttk.Label(ctrls, text=i18n.tr(label_key, self._lang)).grid(row=r, column=0, sticky="e", padx=(0, 6), pady=2)
            var = tk.StringVar()
            ttk.Entry(ctrls, textvariable=var, width=52).grid(row=r, column=1, sticky="we", pady=2)
            ttk.Button(ctrls, text="...", width=3, command=lambda v=var: self._browse_file(v)).grid(row=r, column=2, padx=(4, 0))
            self._cfg_vars[key] = var
            r += 1
        checks = ttk.Frame(ctrls)
        checks.grid(row=r, column=0, columnspan=3, sticky="w", pady=(4, 0))
        for key, label_key, kind in INLINE_FIELDS:
            if kind != "bool":
                continue
            var = tk.BooleanVar()
            ttk.Checkbutton(checks, text=i18n.tr(label_key, self._lang), variable=var).pack(side="left", padx=(0, 16))
            self._cfg_vars[key] = var
        ctrls.columnconfigure(1, weight=1)
        self._reload_form()

    def _build_statusbar(self):
        bar = ttk.Frame(self.root)
        bar.pack(side="bottom", fill="x")
        self.progress = ttk.Progressbar(bar, mode="indeterminate", length=120)
        self.progress.pack(side="right", padx=6, pady=2)
        ttk.Label(bar, textvariable=self.status, anchor="w").pack(side="left", fill="x", expand=True, padx=8)

    def _rebuild_topbar(self):
        """Rebuild the top bar (phase button + inline controls) on a language/project change; the
        log view persists."""
        self._build_topbar()

    # ---- inline controls <-> project doc (only the few INLINE_FIELDS) ---- #
    def _reload_form(self):
        try:
            doc = project.load_doc(self._project_path)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("project.yaml", str(e))
            return
        for key, _label, kind in INLINE_FIELDS:
            if kind == "bool":
                self._cfg_vars[key].set(bool(_get(doc, key)))
            else:
                self._cfg_vars[key].set(_raw_to_str(_get(doc, key), kind))
        self.copy_inputs_var.set(bool(doc.get("copy_inputs_on_save")))
        self._rows = None
        self._params = None

    def _collect_doc(self):
        doc = project.load_doc(self._project_path)        # preserve every other param; set only the inline ones
        for key, _label, kind in INLINE_FIELDS:
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
        self._rebuild_topbar()
        self.status.set(status_msg)

    def _set_language(self):
        self._lang = self.lang_var.get()
        self._update_title()
        self._build_menubar()
        self._rebuild_topbar()
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
        try:                                   # persist the inline file/flag picks so load_params sees them
            project.save_project(self._collect_doc(), self._project_path, copy_inputs=False)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror(i18n.tr("menu_save", self._lang), str(e))
            return
        self._rows = self._params = None
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
