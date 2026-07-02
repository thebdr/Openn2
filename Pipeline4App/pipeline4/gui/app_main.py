"""The PL4 operator window: a toolbar, the phase-button bar, and a Log notebook.

M0 of the GUI port: phases now run on a WORKER THREAD - the handler runs off the Tk main thread and posts
its log/status through a `queue.Queue` drained by `root.after`, so a real run no longer freezes the window
(an indeterminate progressbar + greyed phase buttons mark a run in flight). The phase bar + the dispatch +
Run-all are driven by the `gui/phases.py` registry (one source of the phase order). The log lives in a
`ttk.Notebook` so the Findings / Database Explorer / Files tabs slot in with later milestones.

The backend is fully wired: every phase button runs its real phase. A handler emits via `self._emit`
(thread-safe enqueue) / `self._status` and must NOT touch Tk widgets directly (the drain pump applies them
on the main thread).
"""
from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
import traceback
from tkinter import ttk

from pipeline4.core import config, i18n, severity, treatments
from pipeline4.gui import excel, files_view, findings_view, phases, theme
from pipeline4.gui.db_explorer import DatabaseExplorer
from pipeline4.gui.files_panel import FilesPanel
from pipeline4.gui.findings_panel import FindingsPanel
from pipeline4.gui.documents_panel import DocumentsPanel
from pipeline4.gui.logview import LogView
from pipeline4.gui.phasebar import PhaseBar
from pipeline4.project import project, state

APP_TITLE = "Pipeline4 - SSOT database build"


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
        self._set_title()
        root.geometry(f"{app_ui['width']}x{app_ui['height']}")
        root.protocol("WM_DELETE_WINDOW", self._on_close)   # persist window size + close the tee on exit
        backend = theme.apply_theme(root, self.mode)

        toolbar = ttk.Frame(root)
        toolbar.pack(side="top", fill="x", padx=8, pady=(8, 4))
        ttk.Label(toolbar, text="PIPELINE4", font=(theme.MONO_FONT[0], 14, "bold")).pack(side="left", padx=(2, 14))
        self._tb_project = ttk.Menubutton(toolbar, text=i18n.tr("tb_project", self.lang) + " ▾")
        self._project_menu = tk.Menu(self._tb_project, tearoff=0, postcommand=self._refresh_project_menu)
        self._tb_project.configure(menu=self._project_menu)
        self._tb_project.pack(side="left", padx=(0, 10))
        self._tb_theme = ttk.Button(toolbar, text=i18n.tr("tb_theme", self.lang), command=self._toggle_theme)
        self._tb_theme.pack(side="left", padx=2)
        self._tb_clear = ttk.Button(toolbar, text=i18n.tr("tb_clear_log", self.lang), command=self._clear)
        self._tb_clear.pack(side="left", padx=2)
        self._level_vars = {}                     # the Levels dropdown: a checkbutton per severity level
        self._levels_mb = ttk.Menubutton(toolbar, text=i18n.tr("tb_levels", self.lang) + " ▾")
        levels_menu = tk.Menu(self._levels_mb, tearoff=0)
        for level in severity.LEVELS:             # FAIL, ERROR, WARN, INFO, SKIP, PASS, DEBUG
            forced = level in ("FAIL", "ERROR")   # always shown, greyed out (can't be disabled)
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
        self._backend_label = ttk.Label(toolbar, text=f"theme: {backend}")
        self._backend_label.pack(side="right", padx=2)

        self.phasebar = PhaseBar(root, self._on_phase, self._sub_command, lang=self.lang, mode=self.mode)
        self.phasebar.pack(side="top", fill="x", padx=8, pady=2)

        # the status bar + the busy progressbar live at the bottom (progress just above the status line).
        self.status = ttk.Label(root, text=i18n.tr("st_ready", self.lang), anchor="w", relief="sunken")
        self.status.pack(side="bottom", fill="x")
        self.progress = ttk.Progressbar(root, mode="indeterminate")
        self.progress.pack(side="bottom", fill="x")

        # the Log notebook (Findings / Database Explorer / Files tabs join here in later milestones).
        self.notebook = ttk.Notebook(root)
        self._log_tab = ttk.Frame(self.notebook)
        self.log = LogView(self._log_tab, shown_levels=shown0, font_size=app_ui["font_size"],
                           on_link=self._on_link, on_errtreat=self._on_errtreat)
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
        self.findings = FindingsPanel(self._findings_tab)
        self.findings.pack(side="top", fill="both", expand=True)
        self.notebook.add(self._findings_tab, text=i18n.tr("tab_findings", self.lang))
        self._explorer_tab = ttk.Frame(self.notebook)
        self.explorer = DatabaseExplorer(self._explorer_tab)
        self.explorer.pack(side="top", fill="both", expand=True)
        self.notebook.add(self._explorer_tab, text=i18n.tr("tab_explorer", self.lang))
        self.notebook.pack(side="top", fill="both", expand=True, padx=8, pady=6)

        self.log.append("PHASE", "Pipeline4 - SSOT database build")
        self.log.append("INFO", f"theme backend: {backend}")
        self.log.append("INFO", "Click a phase to run it (on a worker thread), or Run Pipeline for all.")
        if self._log_to_file0:                 # the tee was ON last session - resume it (the log now exists)
            self._enable_log_sink()
            self._tb_logfile.configure(text=self._logfile_label())

        # every themed component subscribes ONCE; theme.set_mode notifies them on a toggle (the manual
        # per-component fan-out in _toggle_theme is retired with the sv-ttk backend).
        for callback in (self.log.set_theme, self.phasebar.set_theme, self.explorer.set_theme,
                         self.files.set_theme, self.documents.set_theme):
            theme.register(callback)

        # the Windows dark/light title bar - applied LAST, after every widget exists, so darktitle's
        # update_idletasks() doesn't flush the ttk styling against a half-built window (PL3 order).
        from pipeline4.gui import darktitle
        darktitle.apply(self.root, self.mode == "dark")

        self.root.after(50, self._drain)

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
            self._set_busy(True, determinate=True, total=len(phases.run_order()))
        else:
            self._set_busy(True)
        threading.Thread(target=self._worker, args=(number, label), daemon=True).start()

    def _worker(self, number, label):
        """Runs OFF the main thread: dispatch to the phase handler (or Run-all); never touch Tk here."""
        self._run_halted = False
        try:
            if number == 0:
                self._run_all()
            else:
                phase = phases.by_number(number)
                handler = getattr(self, phase.handler, None) if (phase and phase.handler) else None
                if handler is None:
                    self._emit("PHASE", f"{number} {label}")
                    self._emit("WARN", f"  phase {number} not implemented yet")
                else:
                    handler()
        except Exception:  # noqa: BLE001 - a handler crash must never take the window down
            self._emit("ERROR", f"handler for {label} crashed:\n{traceback.format_exc()}")
        finally:
            self._q.put(("done",))

    def _run_all(self):
        """Run every runnable phase in dependency order, with live per-phase progress + halt-on-FAIL: a
        phase whose gate halts on a blocking finding sets `self._run_halted`, and the chain stops there
        (the remaining phases are skipped). Each handler is self-contained / re-stages its own
        prerequisites - a future engine optimizes this to a stage-once shared database."""
        order = phases.run_order()
        self._emit("PHASE", f"Run Pipeline ({len(order)} phases)")
        for i, number in enumerate(order, 1):
            phase = phases.by_number(number)
            name = i18n.tr(phase.name_key, self.lang)
            self._status(f"[{i}/{len(order)}] {number} {name}…")
            self._emit("INFO", f"[{i}/{len(order)}] running {number} {name}")
            try:
                getattr(self, phase.handler)()
            except Exception:  # noqa: BLE001 - attribute the crash to THIS phase, stop the chain like a halt
                self._emit("ERROR", f"  {number} {name} crashed:\n{traceback.format_exc()}")
                self._emit("FAIL", f"  Run Pipeline aborted at {number} {name} - "
                                   f"{len(order) - i} remaining phases skipped")
                self._q.put(("progress_step",))
                return
            self._q.put(("progress_step",))
            if self._run_halted:
                self._emit("FAIL", f"  Run Pipeline halted at {number} {name} - "
                                   f"{len(order) - i} remaining phases skipped")
                return
        self._emit("PASS", "  Run Pipeline complete")

    # --- sub-phase + open dispatch (the chevron dropdown buttons) -------------------------------- #
    def _sub_command(self, phase, sub):
        """Resolve a dropdown sub-button to its command for the PhaseBar (None = disabled/greyed). An
        action runs THAT sub-phase (`handler(only=number)`); an `open` startfiles its target."""
        if not sub.enabled:
            return None
        if sub.kind == "open":
            return lambda key=sub.opens: self._on_open(key)
        if sub.kind == "action":
            return lambda n=sub.number: self._on_sub(n)
        if sub.kind == "special" and sub.label_key == "pb_risky_index":
            return lambda: self._on_special("_run_risky_index")
        return None                               # an un-wired "special" (Clean) - not ported -> disabled

    def _on_special(self, handler_name):
        """A GUI-only 'special' (orange) action click (main thread): run it on a worker thread."""
        if self._busy:
            self.log.append("WARN", "  " + i18n.tr("st_running", self.lang))
            return
        self._set_busy(True)
        threading.Thread(target=self._special_worker, args=(handler_name,), daemon=True).start()

    def _special_worker(self, handler_name):
        """Runs OFF the main thread: invoke the named special handler (no `only=`); never crash the window."""
        self._run_halted = False
        try:
            getattr(self, handler_name)()
        except Exception:  # noqa: BLE001
            self._emit("ERROR", f"{handler_name} crashed:\n{traceback.format_exc()}")
        finally:
            self._q.put(("done",))

    def _run_risky_index(self):
        """The MANUAL 'Risky Index Fill' (orange, NOT in the pipeline): over the already-filled I/O List, fill
        each <input required> index by matching it to an existing object index of the same family in the same
        IO node (positional address range), per script_type by ROW ORDER. The filled cells are written RED +
        listed in a `_RiskyIndex` review sheet. A row-order GUESS - REVIEW the sheet."""
        from pipeline4.domain.fillout import fill
        self._status("risky index…")
        label = f"245 {i18n.tr('pb_risky_index', self.lang)}"
        self._emit("PHASE", label)
        res = fill.risky_index_fill()
        self._render(res["findings"])                                  # WARN/INFO only (doc already written)
        backup = f"  (backup {os.path.basename(res['backup'])})" if res.get("backup") else "  (no change)"
        self._emit("WARN", f"  RISKY: filled {res['filled']} index cell(s) by node row-order; "
                           f"{res.get('leftover', 0)} left unresolved -> "
                           f"{os.path.basename(res['output_path'])}{backup}. REVIEW the _RiskyIndex sheet.")

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
            phase = phases.phase_of_sub(number)
            handler = getattr(self, phase.handler, None) if (phase and phase.handler) else None
            if handler is None:
                self._emit("WARN", f"  sub-phase {number} is not runnable")
            else:
                handler(only=number)
        except Exception:  # noqa: BLE001 - a handler crash must never take the window down
            self._emit("ERROR", f"sub-phase {number} crashed:\n{traceback.format_exc()}")
        finally:
            self._q.put(("done",))

    def _open_target(self, key: str) -> str:
        """Resolve an `open` sub-button key to a filesystem path (folder or file)."""
        params = config.load_params()
        return {
            "database": config.database_dir(),
            "error_mgmt": os.path.join(config.user_input_dir(), "error_management.csv"),
            "iolist": params.get("iolist_path", ""),
            "matrix": params.get("matrix_path", ""),
            "validation_logs": config.validation_report_dir(),
            "interfaces": config.interfaces_dir(),
            "io_tags": config.io_tags_dir(),
            "blocks_import": config.blocks_import_dir(),
            "blocks_creation": config.blocks_creation_dir(),
            "diaglist": config.diaglist_dir(),
            "diag_config": config.diagnosis_dir(),
            "hardware": config.hardware_dir(),
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
        menu.add_command(label=i18n.tr("pm_close", self.lang), command=self._project_close,
                         state="normal" if self._project else "disabled")

    def _apply_project_switch(self, root):
        """Re-point everything at the now-active project `root` (None = builtin): retitle + reload the
        Files tree, the Database explorer, and the Findings panel against the new config/Database."""
        self._project = root
        self._set_title()
        self.files.set_sections(self._file_sections())
        self.documents.refresh()                         # the 4 input-doc paths follow the active project
        self.explorer.refresh()
        self.findings.refresh()
        where = project.project_name(root) if root else i18n.tr("pm_builtin", self.lang)
        self.log.append("PHASE", f"project -> {where}")

    def _project_switch_to(self, root):
        try:
            self._apply_project_switch(project.open_project(root))
        except project.ProjectConfigError as error:          # incomplete config -> fail loud + stop
            self.log.append("FAIL", f"  project config incomplete - NOT opened: {root}")
            for rel in error.missing:
                self.log.append("FAIL", f"    missing canonical config file: {rel}")
            self.log.append("FAIL", "  this is a setup/scaffolding error - recreate the project (New Project) "
                                    "so its config is copied complete from the app's builtin config.")
        except (FileNotFoundError, OSError) as error:
            self.log.append("ERROR", f"  could not open project {root}: {error}")

    def _project_open(self):
        from tkinter import filedialog
        chosen = filedialog.askdirectory(parent=self.root, title=i18n.tr("pm_open", self.lang),
                                         initialdir=state.projects_root())
        if not chosen:
            return
        if not project.is_project(chosen):
            self.log.append("ERROR", f"  not a project folder (no config_project/project_params.yaml): {chosen}")
            return
        self._project_switch_to(chosen)

    def _project_new(self):
        from tkinter import filedialog, simpledialog
        parent = filedialog.askdirectory(parent=self.root, title=i18n.tr("pm_new_parent", self.lang),
                                         initialdir=state.projects_root())
        if not parent:
            return
        name = simpledialog.askstring(i18n.tr("pm_new", self.lang), i18n.tr("pm_new_name", self.lang),
                                      parent=self.root)
        if not name or not name.strip():
            return
        try:
            self._apply_project_switch(project.new_project(parent, name.strip()))
        except project.ProjectConfigError as error:          # the scaffold came out incomplete -> fail loud
            self.log.append("FAIL", f"  new project scaffolded INCOMPLETE (missing {', '.join(error.missing)}) "
                                    "- the app's builtin config is itself incomplete; fix the bundled config_project.")
        except (FileExistsError, OSError) as error:
            self.log.append("ERROR", f"  could not create project: {error}")

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
        if busy and determinate:              # Run-all: a real 0..N bar stepped per completed phase
            self.progress.configure(mode="determinate", maximum=max(1, total), value=0)
        elif busy:                            # single phase: an indeterminate bounce
            self.progress.configure(mode="indeterminate")
            self.progress.start(12)
        else:                                 # idle: stop + reset to the indeterminate default
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

    def _render(self, findings) -> None:
        """Apply the registry + post the EFFECTIVE-severity findings as structured records (never halts)."""
        _applied, recs = findings_view.apply_and_records(findings)
        self._q.put(("records", recs))

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
        threading.Thread(target=lambda: excel.goto(path, sheet, cell), daemon=True).start()

    def _on_errtreat(self, uid, level) -> None:
        """A right-click treat on a finding line -> set the treatment + refresh the Findings panel."""
        treatments.set_treatment(uid, level)
        self.findings.refresh()
        self.log.append("INFO", f"  treated {uid} -> {level or 'cleared'} (effective on the next run)")

    # --- the phase handlers (run on the worker thread; emit via self._emit / self._status) ------- #
    def _run_validation(self, only=None):
        """Phase 100. only=None: stage -> the 4 validators -> record the issues + write the 4 reports.
        only=110/120/130/140: run just that validator and render to the log (the header writes the
        reports). only=145: the standalone before/after quality report. Never halts."""
        if only == 145:
            return self._run_change_report()
        from pipeline4.core import config
        from pipeline4.domain import staging
        from pipeline4.domain.validation import crosscheck, iolist, matrix, messages, phase as validation
        if only is None:
            self._emit("PHASE", f"100 {i18n.tr('ph_validation', self.lang)}  (110 + 120 + 130 + 140)")
            self._status("validation…")
            database, _sf = staging.stage()
            res = validation.run_validation(database, lang=self.lang)
            issues = [f for f in res["findings"] if f.severity in ("FAIL", "ERROR", "WARN")]
            self._render(issues)
            c = res["counts"]
            self._emit("PASS", f"  100: {c.get('FAIL', 0)} FAIL, {c.get('ERROR', 0)} ERROR, "
                               f"{c.get('WARN', 0)} WARN, {c.get('PASS', 0)} PASS, {c.get('SKIP', 0)} SKIP "
                               f"-> {res['dir']}")
            return
        self._emit("PHASE", f"{only} {i18n.tr(phases.sub_by_number(only).label_key, self.lang)}")
        self._status("validation…")
        params = config.load_params()
        with messages.active_lang(self.lang):     # build the finding detail in the operator's language
            if only == 110:
                findings = iolist.run_iolist(params)
            elif only == 120:
                findings = matrix.run_ce_matrix(params)
            else:                                  # 130 / 140 read the staged signals
                database, _sf = staging.stage(params)
                runner = crosscheck.run_xcheck_cem_iol if only == 130 else crosscheck.run_xcheck_iol_cem
                findings = runner(database, params)
        issues = [f for f in findings if f.severity in ("FAIL", "ERROR", "WARN")]
        self._render(issues)
        n_pass = sum(1 for f in findings if f.severity == "PASS")
        self._emit("PASS", f"  {only}: {len(issues)} issues + {n_pass} PASS "
                           f"(log only; the 100 header writes the reports)")

    def _run_change_report(self):
        """Phase 100 sub (145) - the STANDALONE before/after quality report (not part of the pipeline).
        Reads the configured current + previous document revisions (`*_previous_path`), classifies the
        changes (matched / intact / corrected / upgrade / removed; systematic re-schemes netted out), and
        writes a graphical HTML dashboard + a CSV audit trail. Never halts; opens the report when done."""
        from pipeline4.domain.changes import run as changes_run
        label = f"145 {i18n.tr('pb_change_report', self.lang)}"
        self._emit("PHASE", label)
        self._status("quality report…")
        res = changes_run.run_change_report()
        iol = res["result"].get("iolist", {})
        if iol.get("available"):
            self._emit("PASS", f"  IoList: {iol['intact']} intact, {iol['correction_count']} corrections "
                               f"({len(iol['regressions'])} value-loss), {iol['upgrade_rows']} upgrade rows, "
                               f"{len(iol['removed'])} removed -> {os.path.basename(res['paths']['html'])}")
        else:
            self._emit("INFO", "  no prior I/O List revision configured (set iolist_previous_path in "
                               f"project_params.yaml) -> {res['dir']}")
        try:
            os.startfile(res["paths"]["html"])           # open the report in the default browser
        except Exception:                                # noqa: BLE001 - opening is best-effort
            pass

    def _run_fill(self, only=None):
        """Phase 200 - Documents Fill Out. The integrated fill: 210 classify (AB Script Type / AC Suggested
        Type), 220 §7 Index (AD), 230/240 §8 Diag Cabinet/Bit (AE/AF) + the DiagnosisBlocks sheet - written
        IN PLACE (surgical, timestamped backup deleted on a value-identical no-op). The phase-200 header runs
        all four; a sub-phase button runs just its leg (230/240 are paired). ph200 writes the DOC only;
        staging re-reads the filled doc (the SSOT). An unresolved row (`<input required>`) is a blocking
        finding (the `_UnresolvedIndex` sheet lists them)."""
        from pipeline4.domain.fillout import fill
        self._status("fill…")
        keys = {210: "pb_fill_script_type", 220: "pb_fill_index",
                230: "pb_fill_diag_cabinet", 240: "pb_fill_diag_bit"}
        label = f"{only or 200} {i18n.tr(keys.get(only, 'ph_fill'), self.lang)}"
        self._emit("PHASE", label)
        res = fill.fill_out(only=only)
        if not self._gate(res["findings"], label=label):
            return
        backup = f"  (backup {os.path.basename(res['backup'])})" if res["backup"] else "  (no change)"
        self._emit("PASS", f"  filled {res['filled']} script type(s), {res['index']} index, {res['diag']} "
                           f"diag; {res['mismatch']} kept (Mode-2); {res['unresolved']} unresolved -> "
                           f"{os.path.basename(res['output_path'])}{backup}")

    def _run_staging(self, only=None):
        """Phase 300: stage the configured I/O List -> the signals table -> Database/signals.csv. The oracle
        splits it: 310 Stage I/O List (`stage_iolist` - I/O List only, no C&E) / 320 Stage C&E Matrix (the
        full staging = I/O List + the Cause&Effect enrichment). 300/320 are byte-identical to the monolith."""
        from pipeline4.core import config
        from pipeline4.domain import staging
        self._status("staging…")
        if only == 310:
            self._emit("PHASE", f"310 {i18n.tr('pb_stage_iolist', self.lang)}")
            database, findings = staging.stage_iolist()
            label = "310 Stage I/O List"
        else:
            key = "pb_stage_cematrix" if only == 320 else "ph_staging"
            self._emit("PHASE", f"{only or 300} {i18n.tr(key, self.lang)}")
            database, findings = staging.stage()
            label = f"{only or 300} staging"
        if not self._gate(findings, label=label):
            return
        signals = database["signals"]
        suffix = "  (I/O List only - run 320 for the C&E)" if only == 310 else ""
        self._emit("PASS", f"  staged {len(signals)} signals{suffix} "
                           f"-> {os.path.join(config.database_dir(), 'signals.csv')}")

    def _run_data_blocks(self, only=None):
        """Phase 500. only=520: stage -> 520 (db_members/db_blocks/instance_dbs + write-back) -> the GlobalDB
        XML. only=510: + build the interface tables and project PLCTags.xlsx. only=None: both. (510 needs the
        520 write-back, so 520 is always built; it's only PROJECTED when 520/None is requested.)"""
        from pipeline4.core import config, run
        from pipeline4.domain import staging, datablocks, datablock_xml, interfaces, io_tags
        label = {510: "510 Generate I/O Tags", 520: "520 Generate Data Blocks"}.get(
            only, "500 Signals Mapping  (520 Data Blocks + 510 I/O Tags)")
        self._emit("PHASE", label)
        self._status("data blocks…")
        findings = []
        database, f = staging.stage(); findings += f
        if not run.has_blocking(f):
            database, f = datablocks.build(database); findings += f
        if not self._gate(findings, label="500 (300 staging + 520 data blocks)"):
            return
        if "db_blocks" not in database:
            self._emit("WARN", "  520 produced no tables (a blocking prereq was downgraded but yielded no data) - nothing further")
            return
        if only in (None, 520):
            n_dbs, n_members = len(database["db_blocks"]), len(database["db_members"])
            self._emit("PASS", f"  {n_members} db_members across {n_dbs} DBs (+ {len(database['instance_dbs'])} "
                               f"instance DBs) -> {os.path.join(config.database_dir(), 'db_members.csv')}")
            count = datablock_xml.project(database)
            self._emit("PASS", f"  projected {count} GlobalDB XMLs -> {config.blocks_import_dir()}")
        if only in (None, 510):
            self._status("I/O tags…")
            database, iface_findings = interfaces.build_interfaces(database)
            res = io_tags.project(database)
            self._render(iface_findings + res["findings"])
            self._emit("PASS", f"  510: {res['total']} I/O tags ({res['io_count']} signal + "
                               f"{res['iface_count']} interface) across {len(res['tables'])} tables -> {config.io_tags_dir()}")

    def _run_interfaces(self, only=None):
        """Phase 400: stage -> 520 -> the interfaces/interface_elements tables -> the IF_*.xlsx projection
        -> (gated) insert each as an IF_ sheet into the I/O List. (410 == the whole phase.)"""
        from pipeline4.core import config, run
        from pipeline4.domain import staging, datablocks, interfaces, interface_xlsx
        self._emit("PHASE", "410 Generate Interfaces" if only == 410 else "400 Interfaces Generation")
        self._status("interfaces…")
        findings = []
        database, f = staging.stage(); findings += f
        if not run.has_blocking(f):
            database, f = datablocks.build(database); findings += f
        if not self._gate(findings, label="400 (300 staging + 520 prereq)"):
            return
        if "db_blocks" not in database:
            self._emit("WARN", "  520 prereq produced no tables (a blocking finding was downgraded but yielded no data) - nothing further")
            return
        database, iface_findings = interfaces.build_interfaces(database)
        self._render(iface_findings)
        result = interface_xlsx.project(database)
        n_if, n_el = len(database["interfaces"]), len(database["interface_elements"])
        self._emit("PASS", f"  {n_if} interfaces, {n_el} mirrored elements -> {len(result['created'])} "
                           f"IF_*.xlsx in {config.interfaces_dir()}")
        params = config.load_params()
        if config.get_param(params, "iolist_params.insert_interface_sheets", False):
            self._status("inserting IF_ sheets…")
            for action in interface_xlsx.insert_interface_sheets(database, iolist_path=params.get("iolist_path")):
                self._emit("WARN" if action.startswith("[WARN]") else "INFO", f"  {action}")
        else:
            self._emit("INFO", "  insert_interface_sheets: disabled (iolist_params.insert_interface_sheets)")

    def _run_diagnosis(self, only=None):
        """Phase 600: stage -> 520 build -> diagnosis.build, then project 610 DiagList_IO/Logic.csv and/or
        620 the OPC SCL. only=610/620 projects just that surface; None does both. (Both need diagnosis.build,
        so it always runs.)"""
        from pipeline4.core import config, run
        from pipeline4.domain import staging, datablocks, diagnosis, diaglist_csv, diagnosis_scl
        label = {610: "610 Generate Diag List", 620: "620 Generate Diag Software Blocks"}.get(
            only, "600 Diagnosis Mapping  (610 DiagList + 620 OPC SCL)")
        self._emit("PHASE", label)
        self._status("diagnosis…")
        findings = []
        database, f = staging.stage(); findings += f
        if not run.has_blocking(f):
            database, f = datablocks.build(database); findings += f
        if not self._gate(findings, label="600 (300 staging + 520 prereq)"):
            return
        if "db_blocks" not in database:
            self._emit("WARN", "  520 prereq produced no tables (a blocking finding was downgraded but yielded no data) - nothing further")
            return
        database, diag_findings = diagnosis.build(database)
        rendered, res, scl = list(diag_findings), None, None
        if only in (None, 610):
            res = diaglist_csv.project(database); rendered += res["findings"]
        if only in (None, 620):
            scl = diagnosis_scl.project(database); rendered += scl["findings"]
        self._render(rendered)
        if res is not None:
            self._emit("PASS", f"  610 DiagList: {res['io_count']} IO + {res['logic_count']} logic rows -> {config.diaglist_dir()}")
        if scl is not None and scl["path"]:
            self._emit("PASS", f"  620 OPC SCL: {scl['entries']} entries across {scl['cabinets']} cabinets -> {scl['path']}")

    def _run_hardware(self, only=None):
        """Phase 700: stage -> hardware.build -> hardware_csv.project (format-2 Stations.csv + Modules.csv).
        710/720 share one extract and each writes BOTH CSVs (like PL3), so only= just changes the label."""
        from pipeline4.core import config, run
        from pipeline4.domain import staging, hardware, hardware_csv
        label = {710: "710 Generate Stations", 720: "720 Generate Modules"}.get(
            only, "700 Hardware Generation  (710 Stations + 720 Modules)")
        self._emit("PHASE", label)
        self._status("hardware…")
        findings = []
        database, f = staging.stage(); findings += f
        if not run.has_blocking(f):
            database, f = hardware.build(database); findings += f
        if not self._gate(findings, label="700 (300 staging + hardware)"):
            return
        if "hardware_stations" not in database:
            self._emit("WARN", "  700 produced no tables (a blocking finding) - nothing further")
            return
        res = hardware_csv.project(database)
        self._emit("PASS", f"  700: {res['stations']} stations + {res['modules']} modules -> {config.hardware_dir()}")

    def _run_software(self, only=None):
        """Phase 800: stage -> 520 -> engine.build. only=820 projects the CreationInfo CSVs + the 03 FC XML +
        the 02_COM safe-DB; only=830 writes InstanceDBs.csv; None does both. (engine.build always runs - both
        surfaces project from it.)"""
        from pipeline4.core import config, run
        from pipeline4.domain import staging, datablocks
        from pipeline4.domain.blocks import engine
        label = {820: "820 Generate Blocks", 830: "830 Generate Instances"}.get(
            only, "800 Software Generation  (820 Blocks + 830 Instances + 02_COM + 03 FC XML)")
        self._emit("PHASE", label)
        self._status("software…")
        findings = []
        database, f = staging.stage(); findings += f
        if not run.has_blocking(f):
            database, f = datablocks.build(database); findings += f
        if not self._gate(findings, label="800 (300 staging + 520 prereq)"):
            return
        if "db_blocks" not in database:
            self._emit("WARN", "  520 prereq produced no tables (a blocking finding was downgraded but yielded no data) - nothing further")
            return
        database, blk_findings = engine.build(database)
        rendered, res, com, inst = list(blk_findings), None, None, None
        if only in (None, 820):
            res = engine.project(database); rendered += res["findings"]
            com = engine.write_com_db(database)
        if only in (None, 830):
            inst = engine.write_instance_dbs(database)
        self._render(rendered)
        if res is not None:
            self._emit("PASS", f"  820: {len(database['software_blocks'])} blocks -> {res['count']} "
                               f"CreationInfo CSVs + {len(res['xml_files'])} FC XML -> {config.blocks_creation_dir()}")
        if com is not None and com["path"]:
            self._emit("PASS", f"  02_COM safe-DB: {com['members']} members -> {com['path']}")
        if inst is not None:
            self._emit("PASS", f"  830 InstanceDBs: {inst['count']} instance DBs -> {inst['path']}")

    def _run_reporting(self, only=None):
        """Phase 900: build the full SSOT (stage -> 520 -> 700; then the WARN-only 400/600/800) then
        coverage.build (the coverage table + ORPHAN/UNPLACED findings) -> coverage.project (the reports).
        (910 == the whole phase.)"""
        from pipeline4.core import config, run
        from pipeline4.domain import staging, datablocks, interfaces, diagnosis, hardware, coverage
        from pipeline4.domain.blocks import engine
        self._emit("PHASE", "910 Generate Pipeline Coverage Report" if only == 910 else "900 Reporting  (910 Pipeline Coverage)")
        self._status("coverage…")
        findings = []
        database, f = staging.stage(); findings += f
        if not run.has_blocking(findings):
            database, f = datablocks.build(database); findings += f
        if not run.has_blocking(findings):
            database, f = hardware.build(database); findings += f
        if not self._gate(findings, label="900 (300 + 520 + 700 prereqs)"):
            return
        if "db_blocks" not in database:
            self._emit("WARN", "  a blocking prereq was downgraded but yielded no data - nothing further")
            return
        proj = []
        database, fi = interfaces.build_interfaces(database); proj += fi
        database, fd = diagnosis.build(database); proj += fd
        database, fb = engine.build(database); proj += fb
        database, fc = coverage.build(database); proj += fc
        res = coverage.project(database)
        self._render(proj)
        st = res["stats"]
        self._emit("PASS", f"  910 coverage: {st['rows']} rows (sig {st['kinds']['signal']}/"
                           f"chan {st['kinds']['channel']}/struct {st['kinds']['structural']}), "
                           f"{st['orphans']} ORPHAN, {st['unplaced']} UNPLACED -> {res['txt']}")

    # --- chrome ---------------------------------------------------------------------------------- #
    def _on_levels_changed(self) -> None:
        """A Levels-dropdown toggle: apply the shown set live + persist it to app_config.yaml (FAIL/ERROR
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
        self._set_title()                                    # re-localize the builtin/project title marker

    def _toggle_theme(self):
        self.mode = "light" if self.mode == "dark" else "dark"
        backend = theme.set_mode(self.root, self.mode)       # tokens + title bar + notify subscribers
        self._backend_label.configure(text=f"theme: {backend}")
        config.save_app_theme(self.mode)                     # remember the choice for next launch
        self.log.append("INFO", f"theme -> {self.mode}")

    def _open_expr_builder(self):
        """Open (or raise) the ƒx Expression Builder (UI_REFRESH_PLAN H)."""
        from pipeline4.gui.expr_builder import ExprBuilder
        if getattr(self, "_fx", None) is not None and self._fx.winfo_exists():
            self._fx.lift()
            return
        self._fx = ExprBuilder(self.root, mode=self.mode)

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
            path = os.path.join(folder, f"pl4_log_{stamp}.txt")
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
