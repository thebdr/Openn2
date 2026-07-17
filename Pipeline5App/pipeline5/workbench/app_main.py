"""The operator window: a toolbar, the phase-button bar, and a Log notebook - the HOST, not the pipeline.

Since step 5 the App owns NO phase logic: the ACTIVE SYSTEM (resolved from the open project's meta
`types`, default Siemens for the builtin config) supplies its PhaseSet (`system.phases` - what the bar
renders and Run-all executes) and its handler table (`system.handlers` - the `run_x(ctx, only=…)`
functions in the system's main.py). The App dispatches clicks to those handlers on a WORKER THREAD,
handing them a PhaseContext whose seams (`emit/status/gate/render/records/halt`) post through a
`queue.Queue` drained by `root.after` - a handler never touches Tk, the window never freezes. A
multi-system project (>1 meta type) gets the toolbar System selector: switching re-points the config
tiers + Database/<sid> + Output/<sid> and re-drives the phase bar from the new system's PhaseSet.
"""
from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
import traceback
from tkinter import ttk

from pipeline5 import config
from pipeline5.language import i18n
from pipeline5.findings import severity
from pipeline5.findings import treatments
from pipeline5.systems.system_contract import PhaseContext
from pipeline5.workbench import excel_goto
from pipeline5.workbench import files_view
from pipeline5.workbench import findings_view
from pipeline5.workbench import theme
from pipeline5.workbench.database_explorer import DatabaseExplorer
from pipeline5.workbench.files_panel import FilesPanel
from pipeline5.workbench.findings_panel import FindingsPanel
from pipeline5.workbench.documents_panel import DocumentsPanel
from pipeline5.workbench.log_view import LogView
from pipeline5.workbench.phasebar import PhaseBar
from pipeline5.project import project_manager as project
from pipeline5.project import app_state as state

APP_TITLE = "Pipeline5 - SSOT database build"


class App:
    def __init__(self, root):
        self.root = root
        self._busy = False
        self._run_halted = False              # set by _gate on a blocking FAIL -> Run-all stops the chain
        self._q: queue.Queue = queue.Queue()
        app_ui = config.load_app_ui()
        self.mode = app_ui["theme"]           # light | dark (live-toggled by the theme button, persisted)
        self.lang = app_ui["language"]        # en | it (live-toggled by the Lang button, persisted)
        self._log_sink = None                 # the open tee file when 'log to file' is ON (host-owned)
        self._log_to_file0 = app_ui["log_to_file"]   # was the tee ON last session? (enabled after the log exists)
        shown0 = app_ui["log_levels"]
        self._project = project.auto_reopen()  # re-point config at the last-opened project (None = builtin)
        self._systems = self._resolve_systems(self._project)  # the project's System objects (meta types)
        self._system = self._systems[0]       # the ACTIVE system (the selector switches it for multi)
        config.use_system(self._system)       # the resolver system tiers + Database/<sid> routing follow
        self._set_title()
        root.geometry(f"{app_ui['width']}x{app_ui['height']}")
        root.protocol("WM_DELETE_WINDOW", self._on_close)   # persist window size + close the tee on exit
        backend = theme.apply_theme(root, self.mode)

        toolbar = ttk.Frame(root)
        toolbar.pack(side="top", fill="x", padx=8, pady=(8, 4))
        ttk.Label(toolbar, text="PIPELINE5", font=(theme.MONO_FONT[0], 14, "bold")).pack(side="left", padx=(2, 14))
        self._tb_project = ttk.Menubutton(toolbar, text=i18n.tr("tb_project", self.lang) + " ▾")
        self._project_menu = tk.Menu(self._tb_project, tearoff=0, postcommand=self._refresh_project_menu)
        self._tb_project.configure(menu=self._project_menu)
        self._tb_project.pack(side="left", padx=(0, 10))
        # the ACTIVE-SYSTEM selector - packed (after Project) only for a multi-system project
        self._sys_var = tk.StringVar()
        self._sys_combo = ttk.Combobox(toolbar, textvariable=self._sys_var, state="readonly", width=26)
        self._sys_combo.bind("<<ComboboxSelected>>", self._on_system_selected)
        self._tb_theme = ttk.Button(toolbar, text=i18n.tr("tb_theme", self.lang), command=self._toggle_theme)
        self._tb_theme.pack(side="left", padx=2)
        self._tb_clear = ttk.Button(toolbar, text=i18n.tr("tb_clear_log", self.lang), command=self._clear)
        self._tb_clear.pack(side="left", padx=2)
        self._level_vars = {}                     # the Levels dropdown: a checkbutton per severity level
        self._levels_mb = ttk.Menubutton(toolbar, text=i18n.tr("tb_levels", self.lang) + " ▾")
        levels_menu = tk.Menu(self._levels_mb, tearoff=0)
        for level in severity.LEVELS:             # FAIL, ERRR, WARN, INFO, SKIP, PASS, DEBG
            forced = level in severity.UNHIDEABLE   # always shown, greyed out (cannot be disabled)
            var = tk.BooleanVar(value=forced or level in shown0)
            self._level_vars[level] = var
            levels_menu.add_checkbutton(label=level, variable=var, command=self._on_levels_changed,
                                        state="disabled" if forced else "normal")
        self._levels_mb.configure(menu=levels_menu)
        self._levels_mb.pack(side="left", padx=6)
        self._tb_lang = ttk.Button(toolbar, text=f"{i18n.tr('tb_lang', self.lang)}: {self.lang.upper()}",
                                   command=self._toggle_lang)
        self._tb_lang.pack(side="left", padx=2)
        self._tb_font_label = ttk.Label(toolbar, text=i18n.tr("tb_font", self.lang))
        self._tb_font_label.pack(side="left", padx=(10, 2))
        self._font_combo = ttk.Combobox(toolbar, width=3, state="readonly",
                                        values=[str(s) for s in config.APP_FONT_SIZES])
        self._font_combo.set(str(app_ui["font_size"]))
        self._font_combo.bind("<<ComboboxSelected>>", self._on_font_size)
        self._font_combo.pack(side="left", padx=2)
        self._tb_logfile = ttk.Button(toolbar, text=self._logfile_label(), command=self._toggle_logfile)
        self._tb_logfile.pack(side="left", padx=(10, 2))
        self._tb_fx = ttk.Button(toolbar, text="ƒx", width=4, command=self._open_expr_builder)
        self._tb_fx.pack(side="left", padx=(10, 2))
        self._tb_help = ttk.Button(toolbar, text="?", width=3, command=self._open_help)
        self._tb_help.pack(side="left", padx=2)
        self._backend_label = ttk.Label(toolbar, text=f"theme: {backend}")
        self._backend_label.pack(side="right", padx=2)

        self.phasebar = PhaseBar(root, self._on_phase, self._sub_command,
                                 phase_set=self._system.phases, lang=self.lang, mode=self.mode)
        self.phasebar.pack(side="top", fill="x", padx=8, pady=2)
        self._refresh_system_selector()

        # the status bar + the busy strip live at the bottom (the pixel CHASE runs while a phase is
        # busy; Run-Pipeline adds its real progress underline).
        from pipeline5.workbench.chasebar import ChaseBar
        self.status = ttk.Label(root, text=i18n.tr("st_ready", self.lang), anchor="w", relief="sunken")
        self.status.pack(side="bottom", fill="x")
        self.progress = ChaseBar(root, mode=self.mode)
        self.progress.pack(side="bottom", fill="x")

        # the Log notebook (Findings / Database Explorer / Files tabs join here in later milestones).
        self.notebook = ttk.Notebook(root)
        self._log_tab = ttk.Frame(self.notebook)
        self.log = LogView(self._log_tab, shown_levels=shown0, font_size=app_ui["font_size"],
                           mode=self.mode, on_link=self._on_link, on_errtreat=self._on_errtreat,
                           on_errjump=self._on_errjump)
        self.log.pack(side="top", fill="both", expand=True)
        self.notebook.add(self._log_tab, text=i18n.tr("tab_log", self.lang))
        self._files_tab = ttk.Frame(self.notebook)
        self.files = FilesPanel(self._files_tab, sections=self._file_sections(),
                                on_status=lambda m: self.status.configure(text=m), mode=self.mode)
        self.files.pack(side="top", fill="both", expand=True)
        self.notebook.add(self._files_tab, text=i18n.tr("tab_files", self.lang))
        self._documents_tab = ttk.Frame(self.notebook)
        self.documents = DocumentsPanel(self._documents_tab, lang=self.lang,
                                        on_status=lambda m: self.status.configure(text=m))
        self.documents.pack(side="top", fill="both", expand=True)
        self.notebook.add(self._documents_tab, text=i18n.tr("tab_documents", self.lang))
        self._findings_tab = ttk.Frame(self.notebook)
        self.findings = FindingsPanel(self._findings_tab, mode=self.mode)
        self.findings.pack(side="top", fill="both", expand=True)
        self.notebook.add(self._findings_tab, text=i18n.tr("tab_findings", self.lang))
        self._explorer_tab = ttk.Frame(self.notebook)
        self.explorer = DatabaseExplorer(self._explorer_tab)
        self.explorer.pack(side="top", fill="both", expand=True)
        self.notebook.add(self._explorer_tab, text=i18n.tr("tab_explorer", self.lang))
        self.notebook.pack(side="top", fill="both", expand=True, padx=8, pady=6)

        self.log.append("PHASE", "Pipeline5 - SSOT database build")
        self.log.append("INFO", f"theme backend: {backend}")
        self.log.append("INFO", "Click a phase to run it (on a worker thread), or Run Pipeline for all.")
        self._warn_stale_imports()             # flag source docs edited after their import (launch check)
        if self._log_to_file0:                 # the tee was ON last session - resume it (the log now exists)
            self._enable_log_sink()
            self._tb_logfile.configure(text=self._logfile_label())

        # every themed component subscribes ONCE; theme.set_mode notifies them on a toggle (the manual
        # per-component fan-out in _toggle_theme is retired with the sv-ttk backend).
        for callback in (self.log.set_theme, self.phasebar.set_theme, self.explorer.set_theme,
                         self.files.set_theme, self.documents.set_theme, self.findings.set_theme,
                         self.progress.set_theme):
            theme.register(callback)

        # the guide (UI_REFRESH_PLAN I): F1 opens the section for the focused area; the attached ids
        # cover whole containers (help_id_of walks up from the focused inner widget).
        from pipeline5.workbench import guide_window as helpwin
        helpwin.attach(self.phasebar, "phase-bar")
        helpwin.attach(self._log_tab, "getting-started")
        helpwin.attach(self._files_tab, "files-tab")
        helpwin.attach(self._documents_tab, "getting-started")
        helpwin.attach(self._explorer_tab, "database-explorer")
        helpwin.attach(self._findings_tab, "treatments")
        root.bind("<F1>", lambda _e: self._open_help())
        helpwin.add_tooltip(self._tb_theme, "Toggle light/dark theme")
        helpwin.add_tooltip(self._levels_mb, "Which log levels the log shows")
        helpwin.add_tooltip(self._tb_lang, "Chrome + findings language (EN/IT)")
        helpwin.add_tooltip(self._tb_logfile, "Tee the log to a timestamped file")
        helpwin.add_tooltip(self._tb_fx, "Expression Builder - author + preview ƒx expressions")
        helpwin.add_tooltip(self._tb_help, "Guide (F1 opens the section for the focused area)")

        # the Windows dark/light title bar - applied LAST, after every widget exists, so darktitle's
        # update_idletasks() doesn't flush the ttk styling against a half-built window (PL3 order).
        from pipeline5.workbench import darktitle
        darktitle.apply(self.root, self.mode == "dark")

        self.root.after(50, self._drain)

    # --- the active system + the handler seams --------------------------------------------------- #
    def _resolve_systems(self, root) -> list:
        """The System objects the project's meta declares (order kept; the FIRST is active on open),
        else the default catalog system - the builtin config / a pre-meta project runs Siemens. The
        open paths (open_project/auto_reopen) already validated every id resolves."""
        from pipeline5.systems import catalog
        systems = project.project_systems(root) if root else []
        return systems or [catalog.by_id("siemens_s7_safety")]

    def _ctx(self) -> PhaseContext:
        """The PhaseContext for one run - the seams a system handler reports through (worker thread):
        everything lands in the queue for the drain pump; nothing touches Tk."""
        return PhaseContext(system=self._system, emit=self._emit, status=self._status,
                            gate=self._gate, render=self._render,
                            records=lambda recs: self._q.put(("records", recs)),
                            halt=self._halt, lang=self.lang)

    def _halt(self) -> None:
        """A handler-declared halt (the severity contract) - Run-all stops the chain here."""
        self._run_halted = True

    # --- the worker-thread run plumbing --------------------------------------------------------- #
    def _emit(self, level: str, message: str) -> None:
        """Thread-safe log sink - enqueue a line for the drain pump (used by handlers + run.gate/render)."""
        self._q.put(("log", level, message))

    def _status(self, text: str) -> None:
        self._q.put(("status", text))

    def _on_phase(self, number, label):
        """A phase-bar click (main thread): start the phase on a worker thread (one at a time)."""
        if self._busy:
            self.log.append("WARN", "  " + i18n.tr("st_running", self.lang))
            return
        # Run-all (0) drives a DETERMINATE progressbar (one step per phase); a single phase bounces.
        if number == 0:
            self._set_busy(True, determinate=True, total=len(self._system.phases.run_order()))
        else:
            self._set_busy(True)
        threading.Thread(target=self._worker, args=(number, label), daemon=True).start()

    def _backup_before(self, label) -> None:
        """The per-BUTTON-PRESS project backup (worker thread): ONE timestamped zip of the FULL project
        beside it per user action (a phase click, Run Pipeline, a sub-phase, a special - never the blue
        open buttons), pruned to `project.backups_kept` (the € knob in project_params.yaml; 0 / builtin
        = off). A backup failure warns and never blocks the run."""
        if not self._project:
            return
        try:
            keep = int(config.get_param(config.load_params(), "project.backups_kept", 0) or 0)
        except Exception:  # noqa: BLE001
            keep = 0
        if keep <= 0:
            return
        try:
            path = project.make_backup(self._project, str(label), keep)
            if path:
                self._emit("INFO", f"  backup -> {os.path.basename(path)}")
        except Exception as exc:  # noqa: BLE001
            self._emit("WARN", f"  project backup failed: {exc}")

    def _worker(self, number, label):
        """Runs OFF the main thread: dispatch to the system's phase handler (or Run-all); never touch
        Tk here."""
        self._run_halted = False
        try:
            if number == 0:
                self._backup_before("run_pipeline")   # one backup per button press, not per chain leg
                self._run_all()
            else:
                phase = self._system.phases.by_number(number)
                handler = self._system.handlers.get(phase.handler) if (phase and phase.handler) else None
                if handler is None:
                    self._emit("PHASE", f"{number} {label}")
                    self._emit("WARN", f"  phase {number} not implemented yet")
                else:
                    self._backup_before(number)
                    handler(self._ctx())
        except Exception:  # noqa: BLE001 - a handler crash must never take the window down
            self._emit("ERRR", f"handler for {label} crashed:\n{traceback.format_exc()}")
        finally:
            self._q.put(("done",))

    def _run_all(self):
        """Run the active system's `run_plan` with live per-phase progress + halt-on-FAIL: a phase whose
        gate halts on a blocking finding sets `self._run_halted`, and the chain stops there (the
        remaining phases are skipped). Each handler is self-contained / re-stages its own
        prerequisites - a future engine optimizes this to a stage-once shared database."""
        order = self._system.phases.run_order()
        self._emit("PHASE", f"Run Pipeline ({len(order)} phases)")
        for i, number in enumerate(order, 1):
            phase = self._system.phases.by_number(number)
            name = i18n.tr(phase.name_key, self.lang)
            self._status(f"[{i}/{len(order)}] {number} {name}…")
            self._emit("INFO", f"[{i}/{len(order)}] running {number} {name}")
            try:
                self._system.handlers[phase.handler](self._ctx())
            except Exception:  # noqa: BLE001 - attribute the crash to THIS phase, stop the chain like a halt
                self._emit("ERRR", f"  {number} {name} crashed:\n{traceback.format_exc()}")
                self._emit("FAIL", f"  Run Pipeline aborted at {number} {name} - "
                                   f"{len(order) - i} remaining phases skipped")
                self._q.put(("progress_step",))
                return
            self._q.put(("progress_step",))
            if self._run_halted:
                self._emit("FAIL", f"  Run Pipeline halted at {number} {name} - "
                                   f"{len(order) - i} remaining phases skipped")
                return
        self._emit("RSLT", "  Run Pipeline complete")

    # --- sub-phase + open dispatch (the chevron dropdown buttons) -------------------------------- #
    def _sub_command(self, phase, sub):
        """Resolve a dropdown sub-button to its command for the PhaseBar (None = disabled/greyed). An
        action runs THAT sub-phase (`handler(only=number)`); an `open` startfiles its target; a wired
        `special` names its System.handlers key in `sub.opens` (unwired specials stay greyed)."""
        if not sub.enabled:
            return None
        if sub.kind == "open":
            return lambda key=sub.opens: self._on_open(key)
        if sub.kind == "action":
            return lambda n=sub.number: self._on_sub(n)
        if sub.kind == "special" and sub.opens:
            return lambda key=sub.opens: self._on_special(key)
        return None                               # an un-wired "special" (Clean) - not ported -> disabled

    def _on_special(self, handler_key):
        """A 'special' (orange) action click (main thread): run its standalone handler on a worker thread."""
        if self._busy:
            self.log.append("WARN", "  " + i18n.tr("st_running", self.lang))
            return
        self._set_busy(True)
        threading.Thread(target=self._special_worker, args=(handler_key,), daemon=True).start()

    def _special_worker(self, handler_key):
        """Runs OFF the main thread: invoke the special's System handler (no `only=`); never crash the
        window."""
        self._run_halted = False
        try:
            handler = self._system.handlers.get(handler_key)
            if handler is None:
                self._emit("WARN", f"  special {handler_key!r} is not wired for this system")
            else:
                self._backup_before(handler_key)
                handler(self._ctx())
        except Exception:  # noqa: BLE001
            self._emit("ERRR", f"{handler_key} crashed:\n{traceback.format_exc()}")
        finally:
            self._q.put(("done",))

    def _on_sub(self, number):
        """A dropdown action click (main thread): run ONE sub-phase on a worker thread. The owning phase
        handler builds the prerequisites, then runs only this sub-phase (`only=number`)."""
        if self._busy:
            self.log.append("WARN", "  " + i18n.tr("st_running", self.lang))
            return
        self._set_busy(True)
        threading.Thread(target=self._sub_worker, args=(number,), daemon=True).start()

    def _sub_worker(self, number):
        """Runs OFF the main thread: dispatch a sub-phase to its parent handler with `only=number`."""
        self._run_halted = False
        try:
            phase = self._system.phases.phase_of_sub(number)
            handler = self._system.handlers.get(phase.handler) if (phase and phase.handler) else None
            if handler is None:
                self._emit("WARN", f"  sub-phase {number} is not runnable")
            else:
                self._backup_before(number)
                handler(self._ctx(), only=number)
        except Exception:  # noqa: BLE001 - a handler crash must never take the window down
            self._emit("ERRR", f"sub-phase {number} crashed:\n{traceback.format_exc()}")
        finally:
            self._q.put(("done",))

    def _open_target(self, key: str) -> str:
        """Resolve an `open` sub-button key to a filesystem path: the ACTIVE SYSTEM first - its
        `open_targets` path-fns, then its `output_layout` delivery dirs - then the kernel targets
        (the neutral Database/ProjectDocumentation trees + the configured documents)."""
        fn = self._system.open_targets.get(key)
        if fn is not None:
            return fn()
        layout = self._system.output_layout.dirs() if self._system.output_layout else {}
        if key in layout:
            return layout[key]
        params = config.load_params()
        return {
            "database": config.database_dir(),
            "error_mgmt": treatments.registry_path(),
            "iolist": params.get("iolist_path", ""),
            "matrix": params.get("matrix_path", ""),
            "validation_logs": config.validation_report_dir(),
            "interfaces": config.interfaces_dir(),
            "diaglist": config.diaglist_dir(),
            "coverage": config.coverage_dir(),
        }.get(key, "")

    def _on_open(self, key: str):
        """An `open` sub-button (main thread): open its folder/file with the OS handler."""
        try:                                      # resolving a target reads params - a missing/malformed
            target = self._open_target(key)       # project file must not escape the Tk callback (future M6)
        except Exception as exc:  # noqa: BLE001
            self.log.append("WARN", f"  could not resolve open target {key}: {exc}")
            return
        if not target or not os.path.exists(target):
            self.log.append("WARN", f"  nothing to open yet: {key} ({target or 'unset'})")
            return
        opener = getattr(os, "startfile", None)   # Windows; degrades gracefully elsewhere
        if opener is None:
            self.log.append("WARN", f"  open is Windows-only here: {target}")
            return
        try:
            opener(target)
            self.log.append("INFO", f"  opened {target}")
        except Exception as exc:  # noqa: BLE001
            self.log.append("WARN", f"  could not open {target}: {exc}")

    # --- the Project Manager (M6) --------------------------------------------------------------- #
    def _set_title(self):
        name = project.project_name(self._project) if self._project else i18n.tr("pm_builtin", self.lang)
        self.root.title(f"{APP_TITLE}  -  {name}")

    def _refresh_project_menu(self):
        """Rebuild the Project ▾ menu each time it opens (so Recent + the active marker stay current)."""
        menu = self._project_menu
        menu.delete(0, "end")
        menu.add_command(label=i18n.tr("pm_new", self.lang) + "…", command=self._project_new)
        menu.add_command(label=i18n.tr("pm_open", self.lang) + "…", command=self._project_open)
        recents = state.recent_projects()
        recent_menu = tk.Menu(menu, tearoff=0)
        for root in recents:
            mark = "• " if self._project and os.path.abspath(root) == os.path.abspath(self._project) else "   "
            recent_menu.add_command(label=f"{mark}{project.project_name(root)}  ({root})",
                                    command=lambda r=root: self._project_switch_to(r))
        if not recents:
            recent_menu.add_command(label=i18n.tr("pm_no_recent", self.lang), state="disabled")
        menu.add_cascade(label=i18n.tr("pm_recent", self.lang), menu=recent_menu)
        menu.add_command(label=i18n.tr("pm_set_root", self.lang) + "…", command=self._project_set_root)
        menu.add_separator()
        menu.add_command(label=i18n.tr("pm_archive", self.lang), command=self._project_archive,
                         state="normal" if self._project else "disabled")
        menu.add_command(label=i18n.tr("pm_save_as", self.lang) + "…", command=self._project_save_as,
                         state="normal" if self._project else "disabled")
        restore_menu = tk.Menu(menu, tearoff=0)
        backups = self._backup_zips()
        for zip_path in backups:
            restore_menu.add_command(label=os.path.basename(zip_path),
                                     command=lambda z=zip_path: self._project_restore(z))
        if not backups:
            restore_menu.add_command(label=i18n.tr("pm_no_backups", self.lang), state="disabled")
        menu.add_cascade(label=i18n.tr("pm_restore", self.lang), menu=restore_menu,
                         state="normal" if self._project else "disabled")
        menu.add_command(label=i18n.tr("pm_close", self.lang), command=self._project_close,
                         state="normal" if self._project else "disabled")

    def _apply_project_switch(self, root):
        """Re-point everything at the now-active project `root` (None = builtin): resolve its systems
        (meta types) and activate the first, re-drive the phase bar + the selector, then retitle +
        reload the Files tree, the Database explorer, and the Findings panel against the new
        config/Database."""
        self._project = root
        self._systems = self._resolve_systems(root)
        self._system = self._systems[0]
        config.use_system(self._system)
        self.phasebar.set_phases(self._system.phases)
        self._refresh_system_selector()
        self._set_title()
        self.files.set_sections(self._file_sections())
        self.documents.refresh()                         # the 4 input-doc paths follow the active project
        self.explorer.refresh()
        self.findings.refresh()
        where = project.project_name(root) if root else i18n.tr("pm_builtin", self.lang)
        self.log.append("PHASE", f"project -> {where}")
        self._warn_stale_imports()

    # --- the multi-system active-system selector -------------------------------------------------- #
    def _refresh_system_selector(self):
        """Show the toolbar System selector only when the open project declares MORE than one system
        type; single-system projects (and the builtin) keep the chrome clean."""
        if len(self._systems) > 1:
            self._sys_combo.configure(values=[i18n.tr(s.name_key, self.lang) for s in self._systems])
            self._sys_var.set(i18n.tr(self._system.name_key, self.lang))
            self._sys_combo.pack(side="left", padx=(0, 10), after=self._tb_project)
        else:
            self._sys_combo.pack_forget()

    def _on_system_selected(self, _event=None):
        """Make the picked system ACTIVE: the config system tiers + the Database/<sid> + Output/<sid>
        routing follow (`use_system`), the phase bar re-drives from its PhaseSet, and the data panels
        reload against the system's trees. Refused while a run is in flight."""
        index = self._sys_combo.current()
        if index < 0 or self._systems[index] is self._system:
            return
        if self._busy:
            self._sys_var.set(i18n.tr(self._system.name_key, self.lang))   # revert the pick
            self.log.append("WARN", "  " + i18n.tr("st_running", self.lang))
            return
        self._system = self._systems[index]
        config.use_system(self._system)
        self.phasebar.set_phases(self._system.phases)
        self.files.set_sections(self._file_sections())
        self.explorer.refresh()
        self.findings.refresh()
        self.log.append("PHASE", f"system -> {i18n.tr(self._system.name_key, self.lang)}")

    def _warn_stale_imports(self) -> None:
        """WARN when an imported document's ORIGINAL source changed after the import (the project copy
        silently diverges) - checked at launch + on every project switch; the Import-documents button
        refreshes the copy from the remembered source."""
        if not self._project:
            return
        try:
            stale = project.stale_imports(self._project)
        except Exception:  # noqa: BLE001 - a malformed meta must not break a project switch
            return
        for key, source in stale:
            self.log.append("WARN", f"  {key.replace('_path', '')}: the original document changed after "
                                    f"it was imported - {source} (Import documents refreshes the copy)")

    def _project_switch_to(self, root):
        try:
            self._apply_project_switch(project.open_project(root))
        except project.UnknownSystemError as error:          # a meta type the registry can't resolve
            self.log.append("FAIL", f"  NOT opened: {error}")
            if error.is_pl4:
                self.log.append("FAIL", "  PL4 projects stay on Pipeline4App - PL5 does not migrate them.")
        except project.ProjectConfigError as error:          # incomplete config -> fail loud + stop
            self.log.append("FAIL", f"  project config incomplete - NOT opened: {root}")
            for rel in error.missing:
                self.log.append("FAIL", f"    missing canonical config file: {rel}")
            self.log.append("FAIL", "  this is a setup/scaffolding error - recreate the project (New Project) "
                                    "so its config is copied complete from the app's builtin config.")
        except (FileNotFoundError, OSError) as error:
            self.log.append("ERRR", f"  could not open project {root}: {error}")

    def _project_open(self):
        from tkinter import filedialog
        chosen = filedialog.askdirectory(parent=self.root, title=i18n.tr("pm_open", self.lang),
                                         initialdir=state.projects_root())
        if not chosen:
            return
        if not project.is_project(chosen):
            self.log.append("ERRR", f"  not a project folder (no config_project/project_params.yaml): {chosen}")
            return
        self._project_switch_to(chosen)

    def _project_new(self):
        """The New-project dialog (type/multi-system/name/base/backups); creation itself is
        project.create_project (the <base>/<name>/<name> double-nested layout + the project meta)."""
        from pipeline5.workbench.new_project import NewProjectDialog
        NewProjectDialog(self.root, lang=self.lang, on_created=self._apply_project_switch)

    def _project_archive(self):
        """Archive Project: a compressed zip of the current project at a user-picked path."""
        from tkinter import filedialog
        if not self._project:
            return
        import datetime
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        initial = f"{project.project_name(self._project)}_{stamp}.zip"
        chosen = filedialog.asksaveasfilename(parent=self.root, title=i18n.tr("pm_archive", self.lang),
                                              defaultextension=".zip", initialfile=initial,
                                              filetypes=(("Zip archive", "*.zip"),))
        if not chosen:
            return
        try:
            count = project.archive_project(self._project, chosen)
        except OSError as error:
            self.log.append("ERRR", f"  archive failed: {error}")
            return
        self.log.append("PASS", "  " + i18n.tr("pm_archived", self.lang, n=count, path=chosen))

    def _backup_zips(self):
        """The current project's backup zips, newest first (feeds the Restore-from-backup submenu)."""
        if not self._project:
            return []
        folder = project.backups_dir(self._project)
        try:
            names = [n for n in os.listdir(folder) if n.lower().endswith(".zip")]
        except OSError:
            return []
        return [os.path.join(folder, n) for n in sorted(names, reverse=True)]

    def _project_save_as(self):
        """Save Project As: copy the WHOLE current project to <base>/<name>/<name> (fresh backup
        history - the zips stay with the original) and switch to the copy. The rename/migrate helper."""
        from tkinter import filedialog, simpledialog
        if not self._project:
            return
        base = filedialog.askdirectory(parent=self.root, title=i18n.tr("pm_save_as", self.lang),
                                       initialdir=os.path.dirname(os.path.dirname(self._project)))
        if not base:
            return
        name = simpledialog.askstring(i18n.tr("pm_save_as", self.lang), i18n.tr("np_name", self.lang),
                                      parent=self.root,
                                      initialvalue=project.project_name(self._project) + "_copy")
        if not name:
            return
        try:
            new_root = project.save_as(self._project, base, name)
        except (ValueError, FileExistsError, OSError, project.ProjectConfigError) as error:
            self.log.append("ERRR", f"  save as failed: {error}")
            return
        self._apply_project_switch(new_root)
        self.log.append("PASS", "  " + i18n.tr("pm_saved_as", self.lang, path=new_root))

    def _project_restore(self, zip_path):
        """Restore a backup: extract it to a NEW sibling folder (the live project is never overwritten)
        and switch to the restored copy."""
        from tkinter import messagebox
        if not self._project:
            return
        if not messagebox.askyesno(i18n.tr("pm_restore", self.lang),
                                   i18n.tr("pm_restore_confirm", self.lang,
                                           name=os.path.basename(zip_path)), parent=self.root):
            return
        try:
            new_root = project.restore_backup(self._project, zip_path)
            opened = project.open_project(new_root)
        except (ValueError, FileExistsError, OSError, project.ProjectConfigError) as error:
            self.log.append("ERRR", f"  restore failed: {error}")
            return
        self._apply_project_switch(opened)
        self.log.append("PASS", "  " + i18n.tr("pm_restored", self.lang, path=opened))

    def _project_set_root(self):
        from tkinter import filedialog
        chosen = filedialog.askdirectory(parent=self.root, title=i18n.tr("pm_set_root", self.lang),
                                         initialdir=state.projects_root())
        if chosen:
            state.set_projects_root(chosen)
            self.log.append("INFO", f"  projects root -> {chosen}")

    def _project_close(self):
        project.close_project()
        self._apply_project_switch(None)

    def _file_sections(self):
        """The Files-tab sections from the `files_tab` config (app_config.yaml; UI_REFRESH_PLAN E),
        compiled + resolved against the ACTIVE config/project. A missing section -> one explanatory
        header and a WARN (the structure is never baked into code); placeholder/regex problems surface
        as WARNs while the rest of the tab keeps working."""
        try:
            params = config.load_params()
        except Exception:  # noqa: BLE001  - a missing/broken project_params must not break the Files tab
            params = {}
        specs = config.load_files_tab()
        if specs is None:
            self.log.append("WARN", "  files_tab section missing in app_config.yaml - the Files tab is empty")
            return [{"title": "files_tab section missing in app_config.yaml",
                     "roots": [], "include": [], "exclude": []}]
        sections, warnings = files_view.sections_from_config(specs, params)
        for warning in warnings:
            self.log.append("WARN", f"  files_tab: {warning}")
        return sections

    def _drain(self):
        """Main thread: apply the queued log/status/done events to the widgets, then reschedule."""
        try:
            while True:
                event = self._q.get_nowait()
                kind = event[0]
                if kind == "log":
                    self.log.append(event[1], event[2])
                elif kind == "records":
                    self.log.append_records(event[1])
                elif kind == "status":
                    self.status.configure(text=event[1])
                elif kind == "progress_step":     # a Run-all per-phase tick (determinate bar)
                    try:
                        self.progress.configure(value=float(self.progress["value"]) + 1)
                    except tk.TclError:
                        pass
                elif kind == "done":
                    self._set_busy(False)
                    self.status.configure(text=i18n.tr("st_ready", self.lang))
                    self.findings.refresh()          # surface the run's findings in the panel
                    self.explorer.refresh()          # reload the SSOT tables the run (re)wrote
                    self.files.refresh()             # the run (re)wrote output files - re-scan the tree
        except queue.Empty:
            pass
        self.root.after(50, self._drain)

    def _set_busy(self, busy: bool, *, determinate: bool = False, total: int = 0):
        self._busy = busy
        self.phasebar.set_enabled(not busy)
        if busy and determinate:              # Run-all: the chase + a real 0..N underline per phase
            self.progress.configure(mode="determinate", maximum=max(1, total), value=0)
            self.progress.start(12)
        elif busy:                            # single phase: the chase alone
            self.progress.configure(mode="indeterminate")
            self.progress.start(12)
        else:                                 # idle: stop + reset
            self.progress.stop()
            self.progress.configure(mode="indeterminate", value=0)

    # --- the GUI gate/render seam (structured, clickable records) -------------------------------- #
    def _gate(self, findings, *, label: str) -> bool:
        """Apply the registry, post the EFFECTIVE-severity findings as structured records to the log, and
        return CONTINUE (False = halt on a blocking effective severity). The records render on the worker
        (pure) and are drained into the clickable LogView on the main thread."""
        applied, recs = findings_view.apply_and_records(findings)
        self._q.put(("records", recs))
        if treatments.should_halt(applied):
            self._emit("FAIL", f"  {label} halted on a blocking finding - nothing written")
            self._run_halted = True           # Run-all reads this to stop the remaining chain
            return False
        return True

    def _render(self, findings, *, label: str = "") -> None:
        """Apply the registry + post the EFFECTIVE-severity findings as structured records. The severity
        CONTRACT (user spec): FAIL always HALTS THE PIPELINE - even from a projection/report phase whose
        output is already on disk (the halt stops the RUN and marks the output suspect; it cannot
        unwrite). ERRR/WARN/… never halt. `_gate` is the pre-write variant (halt BEFORE writing)."""
        applied, recs = findings_view.apply_and_records(findings)
        self._q.put(("records", recs))
        if treatments.should_halt(applied):
            self._run_halted = True           # Run-all stops the chain here
            self._emit("FAIL", f"  {label or 'phase'}: a FAIL-severity finding HALTS the pipeline - "
                               "the output written above is SUSPECT, review it before use")

    # --- log link callbacks (main thread) ------------------------------------------------------- #
    def _resolve_doc(self, basename: str) -> str:
        params = config.load_params()
        for path in (params.get("iolist_path"), params.get("matrix_path")):
            if path and os.path.basename(path) == basename:
                return path
        return ""

    def _on_link(self, doc, sheet, cell) -> None:
        """A clicked Sheet!Cell log link -> open the workbook in Excel at that cell (off-thread; COM)."""
        path = self._resolve_doc(doc)
        if not path:
            self.log.append("WARN", f"  cannot locate workbook '{doc}'")
            return
        threading.Thread(target=lambda: excel_goto.goto(path, sheet, cell), daemon=True).start()

    def _on_errtreat(self, uid, level) -> None:
        """A right-click treat on a finding line -> set the treatment + refresh the Findings panel."""
        treatments.set_treatment(uid, level)
        self.findings.refresh()
        self.log.append("INFO", f"  treated {uid} -> {level or 'cleared'} (effective on the next run)")

    def _on_errjump(self, uid) -> None:
        """A LEFT-click on a finding line's [LEVEL] -> open the Findings tab at that finding's row
        (the panel drops its filters if they hide it)."""
        self.notebook.select(self._findings_tab)
        if not self.findings.focus_uid(uid):
            self.log.append("WARN", f"  finding {uid} is not in the recorded validation_issues "
                                    "(re-run its phase to refresh the table)")

    # --- chrome ---------------------------------------------------------------------------------- #
    def _on_levels_changed(self) -> None:
        """A Levels-dropdown toggle: apply the shown set live + persist it to app_config.yaml (FAIL/ERRR
        are always included)."""
        levels = {level for level, var in self._level_vars.items() if var.get()}
        self.log.set_shown_levels(levels)
        config.save_app_log_levels(levels)

    def _toggle_lang(self):
        """Flip EN<->IT: persist, re-translate the bar + the toolbar/tabs/status chrome live."""
        self.lang = "it" if self.lang == "en" else "en"
        config.save_app_language(self.lang)
        self.phasebar.set_lang(self.lang)
        self._retranslate_chrome()
        self.status.configure(text=i18n.tr("st_language", self.lang, code=self.lang))

    def _on_font_size(self, _event=None):
        """The Font dropdown: resize the log viewer live + persist the choice to app_config.yaml."""
        try:
            size = int(self._font_combo.get())
        except (TypeError, ValueError):
            return
        self.log.set_font_size(size)
        config.save_app_font_size(size)

    def _retranslate_chrome(self):
        """Re-label the persistent chrome (toolbar buttons + notebook tabs) for the current language."""
        self._tb_theme.configure(text=i18n.tr("tb_theme", self.lang))
        self._tb_clear.configure(text=i18n.tr("tb_clear_log", self.lang))
        self._levels_mb.configure(text=i18n.tr("tb_levels", self.lang) + " ▾")
        self._tb_font_label.configure(text=i18n.tr("tb_font", self.lang))
        self._tb_lang.configure(text=f"{i18n.tr('tb_lang', self.lang)}: {self.lang.upper()}")
        self._tb_logfile.configure(text=self._logfile_label())
        self._tb_project.configure(text=i18n.tr("tb_project", self.lang) + " ▾")
        self.notebook.tab(self._log_tab, text=i18n.tr("tab_log", self.lang))
        self.notebook.tab(self._files_tab, text=i18n.tr("tab_files", self.lang))
        self.notebook.tab(self._documents_tab, text=i18n.tr("tab_documents", self.lang))
        self.notebook.tab(self._findings_tab, text=i18n.tr("tab_findings", self.lang))
        self.notebook.tab(self._explorer_tab, text=i18n.tr("tab_explorer", self.lang))
        self.documents.set_lang(self.lang)                   # the picker labels + Browse/Clear buttons
        self._refresh_system_selector()                      # the selector shows localized system names
        self._set_title()                                    # re-localize the builtin/project title marker

    def _toggle_theme(self):
        self.mode = "light" if self.mode == "dark" else "dark"
        backend = theme.set_mode(self.root, self.mode)       # tokens + title bar + notify subscribers
        self._backend_label.configure(text=f"theme: {backend}")
        config.save_app_theme(self.mode)                     # remember the choice for next launch
        self.log.append("INFO", f"theme -> {self.mode}")

    def _open_expr_builder(self):
        """Open (or raise) the ƒx Expression Builder (UI_REFRESH_PLAN H)."""
        from pipeline5.workbench.expr_builder import ExprBuilder
        if getattr(self, "_fx", None) is not None and self._fx.winfo_exists():
            self._fx.lift()
            return
        self._fx = ExprBuilder(self.root, mode=self.mode)

    def _open_help(self, _event=None):
        """F1 / the ? button: the guide at the focused area's section (default: getting-started)."""
        from pipeline5.workbench import guide_window as helpwin
        try:
            widget = self.root.focus_get()
        except (KeyError, tk.TclError):            # a foreign/menu focus - fall to the default section
            widget = None
        section = helpwin.help_id_of(widget) or "getting-started"
        helpwin.open_section(self.root, section, mode=self.mode)

    # --- log-to-file tee (M7) ------------------------------------------------------------------- #
    def _logfile_label(self) -> str:
        state = "ON" if self._log_sink is not None else "OFF"
        return f"{i18n.tr('tb_log_to_file', self.lang)}: {state}"

    def _enable_log_sink(self) -> None:
        """Open a timestamped log file under the reports tree and tee the log into it. Best-effort."""
        import datetime
        try:
            folder = config.gui_log_dir()
            os.makedirs(folder, exist_ok=True)
            stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            path = os.path.join(folder, f"pl5_log_{stamp}.txt")
            self._log_sink = open(path, "w", encoding="utf-8")
            self.log.set_sink(self._log_sink)
            self.log.append("INFO", f"  log -> {path}")
        except OSError as exc:
            self._log_sink = None
            self.log.set_sink(None)
            self.log.append("WARN", f"  could not open log file: {exc}")

    def _disable_log_sink(self) -> None:
        self.log.set_sink(None)
        if self._log_sink is not None:
            try:
                self._log_sink.close()
            except OSError:
                pass
            self._log_sink = None

    def _toggle_logfile(self) -> None:
        """Toggle the live 'log to file' tee, and persist the choice for next launch."""
        if self._log_sink is None:
            self._enable_log_sink()
        else:
            name = os.path.basename(getattr(self._log_sink, "name", "") or "")
            self._disable_log_sink()
            self.log.append("INFO", f"  log file closed{(': ' + name) if name else ''}")
        config.save_app_log_to_file(self._log_sink is not None)
        self._tb_logfile.configure(text=self._logfile_label())

    def _on_close(self) -> None:
        """Persist the window size + close the log tee, then destroy the window."""
        try:
            config.save_app_window_size(self.root.winfo_width(), self.root.winfo_height())
        except Exception:                                    # noqa: BLE001 - never block a clean exit
            pass
        self._disable_log_sink()
        self.root.destroy()

    def _clear(self):
        self.log.clear()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()
