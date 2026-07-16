"""The New-project dialog: project type(s) (the RTX types are declared but greyed until their
pipelines exist), the Multi-System Controller toggle (allows selecting more than one type), the name,
the base folder - the project lands at `<base>/<name>/<name>` (the DOUBLE nesting is deliberate: the
outer folder is the project's own root where the per-phase timestamped backups live beside the live
copy) - and the € knob 'backups kept' (editable later in project_params.yaml -> project.backups_kept).

The create logic is `project.create_project` (Tk-free, tested); this is the Tk shell.
"""
from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk, filedialog

from pipeline5.language import i18n
from pipeline5.workbench import theme
from pipeline5.project import project_manager as project
from pipeline5.project import app_state as state



def _type_rows(lang: str) -> list:
    """The project-type rows [(id, label, available)], DERIVED from the systems registry
    (availability = catalog membership - C-021); labels via i18n from each row's name_key."""
    from pipeline5.systems import catalog
    return [(sid, i18n.tr(key, lang), available) for sid, key, available in catalog.catalog()]

class NewProjectDialog(tk.Toplevel):
    def __init__(self, parent, lang: str = "en", on_created=lambda _root: None):
        super().__init__(parent)
        self.lang = lang
        self._on_created = on_created
        self.title(i18n.tr("np_title", lang))
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)

        # --- project type(s) ---------------------------------------------------------------- #
        ttk.Label(body, text=i18n.tr("np_type", lang)).grid(row=0, column=0, sticky="nw", pady=(0, 2))
        self._type_rows = _type_rows(lang)
        self._types = tk.Listbox(body, height=len(self._type_rows), exportselection=False,
                                 selectmode="browse", activestyle="none")
        for type_id, label, available in self._type_rows:
            self._types.insert("end", label)
            if not available:
                self._types.itemconfig("end", foreground=theme.color("disabled_fg"))
        self._types.selection_set(0)
        self._types.bind("<<ListboxSelect>>", self._enforce_selection)
        self._types.grid(row=0, column=1, columnspan=2, sticky="ew", pady=(0, 4))

        self._multi = tk.BooleanVar(value=False)
        ttk.Checkbutton(body, text=i18n.tr("np_multi", lang), variable=self._multi,
                        command=self._on_multi).grid(row=1, column=1, columnspan=2, sticky="w",
                                                     pady=(0, 8))

        # --- name + base folder + live path preview ------------------------------------------ #
        ttk.Label(body, text=i18n.tr("np_name", lang)).grid(row=2, column=0, sticky="w")
        self._name = ttk.Entry(body, width=38)
        self._name.grid(row=2, column=1, columnspan=2, sticky="ew", pady=2)
        self._name.bind("<KeyRelease>", lambda _e: self._refresh_preview())

        ttk.Label(body, text=i18n.tr("np_base", lang)).grid(row=3, column=0, sticky="w")
        self._base = ttk.Entry(body)
        self._base.insert(0, state.projects_root())
        self._base.configure(state="readonly")
        self._base.grid(row=3, column=1, sticky="ew", pady=2)
        ttk.Button(body, text="…", width=3, command=self._pick_base).grid(row=3, column=2, padx=(4, 0))

        ttk.Label(body, text=i18n.tr("np_path", lang)).grid(row=4, column=0, sticky="w")
        self._preview = ttk.Label(body, text="", foreground=theme.color("accent"))
        self._preview.grid(row=4, column=1, columnspan=2, sticky="w", pady=(2, 8))

        # --- backups kept (the € knob) -------------------------------------------------------- #
        ttk.Label(body, text=i18n.tr("np_backups", lang)).grid(row=5, column=0, sticky="w")
        self._backups = tk.Spinbox(body, from_=0, to=project.BACKUPS_KEPT_MAX, width=5)
        self._backups.delete(0, "end")
        self._backups.insert(0, str(project.BACKUPS_KEPT_DEFAULT))
        self._backups.grid(row=5, column=1, sticky="w", pady=2)
        hint = ttk.Label(body, text="€  " + i18n.tr("np_backups_hint", lang),
                         foreground=theme.color("disabled_fg"), wraplength=420, justify="left")
        hint.grid(row=6, column=1, columnspan=2, sticky="w", pady=(0, 8))

        # --- error line + buttons ------------------------------------------------------------- #
        self._error = ttk.Label(body, text="", foreground="#ff6b6b")
        self._error.grid(row=7, column=0, columnspan=3, sticky="w")
        buttons = ttk.Frame(body)
        buttons.grid(row=8, column=0, columnspan=3, sticky="e", pady=(8, 0))
        ttk.Button(buttons, text=i18n.tr("np_create", lang), command=self._create).pack(side="left")
        ttk.Button(buttons, text=i18n.tr("np_cancel", lang),
                   command=self.destroy).pack(side="left", padx=(8, 0))

        self._refresh_preview()
        self._name.focus_set()
        self.bind("<Return>", lambda _e: self._create())
        self.bind("<Escape>", lambda _e: self.destroy())

    # --- selection rules ---------------------------------------------------------------------- #
    def _enforce_selection(self, _event=None) -> None:
        """Drop greyed (unavailable) picks; without Multi-System keep a single selection."""
        chosen = list(self._types.curselection())
        for index in chosen:
            if not self._type_rows[index][2]:
                self._types.selection_clear(index)
        chosen = list(self._types.curselection())
        if not self._multi.get() and len(chosen) > 1:
            for index in chosen[1:]:
                self._types.selection_clear(index)

    def _on_multi(self) -> None:
        self._types.configure(selectmode="extended" if self._multi.get() else "browse")
        self._enforce_selection()

    # --- fields --------------------------------------------------------------------------------- #
    def _pick_base(self) -> None:
        chosen = filedialog.askdirectory(parent=self, title=i18n.tr("np_base", self.lang),
                                         initialdir=self._base.get() or state.projects_root())
        if chosen:
            self._base.configure(state="normal")
            self._base.delete(0, "end")
            self._base.insert(0, chosen)
            self._base.configure(state="readonly")
            self._refresh_preview()

    def _refresh_preview(self) -> None:
        name = self._name.get().strip()
        base = self._base.get().strip()
        shown = os.path.join(base or "…", name or "…", name or "…")
        self._preview.configure(text=shown)
        problem = project.validate_name(name) if name else ""
        self._error.configure(text=problem)

    def _selected_types(self) -> list:
        return [self._type_rows[i][0] for i in self._types.curselection()
                if self._type_rows[i][2]]

    # --- create ---------------------------------------------------------------------------------- #
    def _create(self) -> None:
        name = self._name.get().strip()
        base = self._base.get().strip()
        types = self._selected_types()
        problem = project.validate_name(name)
        if not problem and not base:
            problem = i18n.tr("np_err_no_base", self.lang)
        if not problem and not types:
            problem = i18n.tr("np_err_no_type", self.lang)
        if problem:
            self._error.configure(text=problem)
            return
        try:
            backups = int(self._backups.get())
        except (TypeError, ValueError):
            backups = project.BACKUPS_KEPT_DEFAULT
        try:
            root = project.create_project(base, name, types, self._multi.get(), backups)
        except (ValueError, FileExistsError, OSError, project.ProjectConfigError) as error:
            self._error.configure(text=str(error))
            return
        self.destroy()
        self._on_created(root)
