#!/usr/bin/env python3
"""_app_tabs.py - the Configuration/Files-tab half of pipeline2.gui.gui.App.

`TabsMixin` holds the Configuration-tab and Files-tab builders, the params
load/save round-trip, the project-manager actions and the `_open_*` helpers.
It is mixed into `App` in gui.py; every method here runs as a method of `App`
and uses `self.*`, so the split is purely cosmetic (no behaviour change).  The
shared module-level names and the gui-local helpers/constants are imported from
`pipeline2.gui.gui`, which is already fully populated by the time gui.py pulls
this mixin in.
"""
from __future__ import annotations
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from pipeline2.core import config, i18n
from pipeline2.gui import editor
from pipeline2.gui import project
from pipeline2.gui import gui_common
from pipeline2.blocks import block_templates  # noqa: F401  (parity with the original namespace)
from pipeline2.blocks import blockshells

# gui-local names (helpers + constants) - gui.py defines these before it imports
# this mixin, so the import is resolved against the partially-initialised module.
from pipeline2.gui.gui import PARAM_SPEC, _get, _set


class TabsMixin:
    # ---- widget construction ------------------------------------------- #
    def _build_files_tab(self, parent):
        """Spreadsheet/CSV/text editor over the config and output files."""
        roots = [("config", config.CONFIG_DIR)]
        try:
            dtd = config.load_params(self._project_path).get("device_types_db")
            if dtd and os.path.isdir(os.path.dirname(dtd)):
                roots.append(("HardwareConfigBuilderData", os.path.dirname(dtd)))
        except Exception:  # noqa: BLE001
            pass
        roots.append(("Output", self._out_dir()))
        self._files = editor.FileBrowser(parent, roots, on_status=self.status.set)
        self._files.pack(fill="both", expand=True)

    def _build_config_tab(self, parent):
        ttk.Label(parent, text="project_params.yaml", font=("Segoe UI", 10, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 6))
        self._cfg_vars: dict[str, tk.StringVar] = {}
        try:
            raw = project.load_doc(self._project_path)
        except Exception as e:  # noqa: BLE001
            raw = {}
            messagebox.showerror("params.yaml", f"could not read params.yaml:\n{e}")

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
        ttk.Button(btns, text="Save params.yaml", command=self._save_params).pack(side="left")
        ttk.Button(btns, text="Reload", command=self._reload_params).pack(side="left", padx=6)
        ttk.Separator(btns, orient="vertical").pack(side="left", fill="y", padx=10)
        ttk.Button(btns, text="Open signal_types.csv",
                   command=lambda: self._open_path(os.path.join(config.INPUT_DOCS_DIR, "signal_types.csv"))).pack(side="left", padx=2)
        ttk.Button(btns, text="Open column_map.csv",
                   command=lambda: self._open_path(os.path.join(config.INPUT_DOCS_DIR, "column_map.csv"))).pack(side="left", padx=2)
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
                   command=lambda: self._open_in_files(config.BLOCK_TEMPLATES_JSON)
                   ).grid(row=1, column=1, sticky="w", padx=6, pady=2)
        b_central = ttk.Button(blk, text="Export Central Database (CSV)",
                               command=lambda: self._start(self._work_export_central))
        b_central.grid(row=1, column=2, sticky="w", padx=6, pady=2)
        ttk.Button(blk, text="Open Central Database",
                   command=self._open_central).grid(row=1, column=3, sticky="w", padx=6, pady=2)
        b_blocks = ttk.Button(blk, text="Generate SoftwareBlocks CSV",
                              command=lambda: self._start(self._work_softwareblocks))
        b_blocks.grid(row=2, column=0, sticky="w", padx=(0, 6), pady=2)
        b_cov = ttk.Button(blk, text="Coverage report",
                           command=lambda: self._start(self._work_coverage))
        b_cov.grid(row=2, column=1, sticky="w", padx=6, pady=2)
        ttk.Button(blk, text="Open coverage report",
                   command=self._open_coverage).grid(row=2, column=2, sticky="w", padx=6, pady=2)
        b_shells = ttk.Button(blk, text="Generate block shells (.xlsm)",
                              command=lambda: self._start(self._work_shells))
        b_shells.grid(row=3, column=0, sticky="w", padx=(0, 6), pady=2)
        ttk.Button(blk, text="Open shell workbook",
                   command=lambda: self._open_path(blockshells.shell_path())).grid(row=3, column=1, sticky="w", padx=6, pady=2)
        self._run_buttons.extend([b_scan, b_central, b_blocks, b_cov, b_shells])  # greyed while a run is in flight

    def _open_in_files(self, path: str):
        """Open a file in the Files tab editor (switch to it); else open externally."""
        files = getattr(self, "_files", None)
        if files is not None and os.path.exists(path):
            self._nb.select(self._files_tab)
            files.editor.open(path)
        else:
            self._open_path(path)

    def _open_central(self):
        path = config.out_path(self._out_dir(), "io_database")
        if os.path.exists(path):
            self._open_in_files(path)
        else:
            self.status.set("IODatabase.csv not found - run 'Export Central Database' first")

    def _open_coverage(self):
        path = config.out_path(self._out_dir(), "coverage_report") + ".csv"
        if os.path.exists(path):
            self._open_in_files(path)
        else:
            self.status.set("io_project_coverage_report.csv not found - run 'Coverage report' first")

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
            items = [p.strip() for p in text.split(",") if p.strip()]
            # flow style ("[a, b]") matches params.yaml and keeps any trailing/section
            # comment on the key intact (a block list would push items past it).
            from ruamel.yaml.comments import CommentedSeq
            seq = CommentedSeq(items)
            seq.fa.set_flow_style()
            return seq
        return text

    def _browse_file(self, var: tk.StringVar):
        p = filedialog.askopenfilename(title="Select file")
        if p:
            var.set(os.path.normpath(p))

    def _browse_dir(self, var: tk.StringVar):
        p = filedialog.askdirectory(title="Select folder")
        if p:
            var.set(os.path.normpath(p))

    def _collect_doc(self):
        """The current project doc (ruamel round-trip) with the config-tab edits applied."""
        try:
            raw = project.load_doc(self._project_path)
        except Exception:  # noqa: BLE001
            raw = {}
        for key, _label, kind in PARAM_SPEC:
            _set(raw, key, self._str_to_raw(self._cfg_vars[key].get(), kind))
        raw["copy_inputs_on_save"] = bool(self.copy_inputs_var.get())
        raw["language"] = self._lang
        return raw

    def _save_params(self):
        # round-trip through ruamel (comments + key order survive); honour copy-inputs-on-save
        try:
            project.save_project(self._collect_doc(), self._project_path,
                                 copy_inputs=bool(self.copy_inputs_var.get()))
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Save failed", str(e))
            return
        self._rows = None  # config changed -> re-stage next run
        self._reload_params()                  # reflect any copy-inputs path rewrite
        self._log("OK", "project saved (staged rows invalidated).", None)
        self.status.set("project saved")

    def _reload_params(self):
        try:
            raw = project.load_doc(self._project_path)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("params.yaml", str(e))
            return
        for key, _label, kind in PARAM_SPEC:
            self._cfg_vars[key].set(self._raw_to_str(_get(raw, key), kind))
        self.copy_inputs_var.set(bool(raw.get("copy_inputs_on_save")))
        self.status.set("project reloaded")

    # ---- project manager actions --------------------------------------- #
    def _proj_new(self):
        folder = filedialog.askdirectory(title=i18n.tr("menu_new", self._lang))
        if not folder:
            return
        self._project_path = project.new_project(folder)
        self._after_project_change()

    def _proj_open(self):
        folder = filedialog.askdirectory(title=i18n.tr("menu_open", self._lang))
        if not folder:
            return
        try:
            self._project_path = project.open_project(folder)
        except FileNotFoundError:
            messagebox.showerror(i18n.tr("menu_open", self._lang),
                                 f"{project.PROJECT_FILE} not found in:\n{folder}")
            return
        self._after_project_change()

    def _proj_save_as(self):
        folder = filedialog.askdirectory(title=i18n.tr("menu_save_as", self._lang))
        if not folder:
            return
        try:
            self._project_path = project.save_project_as(self._collect_doc(), folder,
                                                         copy_inputs=bool(self.copy_inputs_var.get()))
        except Exception as e:  # noqa: BLE001
            messagebox.showerror(i18n.tr("menu_save_as", self._lang), str(e))
            return
        self._after_project_change()

    def _proj_archive(self):
        res = gui_common.ask_archive(self.root, project.project_name(self._project_path), self._lang)
        if not res:
            return
        try:
            zpath = project.archive_project(self._project_path, res["name"], res["add_datetime"])
        except Exception as e:  # noqa: BLE001
            messagebox.showerror(i18n.tr("menu_archive", self._lang), str(e))
            return
        self.status.set(i18n.tr("archive_done", self._lang, path=zpath))

    def _set_language(self):
        self._lang = self.lang_var.get()
        self._build_menubar()
        self._build_cascade()                # relabel the cascade buttons
        self.status.set("Ready")

    def _after_project_change(self):
        self._rows = None
        self._params = None                  # don't keep the previous project's params/out dir
        self._lang = self._read_language()
        self.lang_var.set(self._lang)
        self.copy_inputs_var.set(self._read_copy_inputs())
        self._build_menubar()
        self._build_cascade()                # relabel in the new project's language
        self._reload_params()
        self._update_title()
        self._log("INFO", f"project: {self._project_path}", None)

    def _open_dtd(self):
        try:
            params = config.load_params(self._project_path)
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
