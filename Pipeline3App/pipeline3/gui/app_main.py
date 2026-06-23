"""app_main.py - the Pipeline3 operator window (the interactive twin of the CLI).

The app is **Pipeline3**; each profile is a named session shown in the title + log banner as
"Pipeline3 - <session> (<profile>)": the main operator session is **Broski Session (main)**, the
slim designer session is **IOList & CEMatrix Validation (designer)**.

A dark-by-default window (dark title bar too) whose top **phase bar is generated from the phase
registry** (`phasebar.build_spec` over `registry().presentation_order()`), with the pink Run-Pipeline
master on the left. A phase header runs the whole phase; its chevron dropdown lists that phase's
buttons (action steps / opens / specials). The pipeline runs on a worker thread; its `emit` output is
queued and drained into the `LogView` on the Tk main thread. Font: bundled Monaspace Neon; theme: sv-ttk.

Slice 2 (Main GUI polish): EN/IT relabel toggle + dark/light toggle (live re-theme incl. the title
bar), clickable Sheet!Cell log links (open the I/O List in Excel via COM), and full open-artifact
wiring. Still deferred: YAML-explorer config, Files tab, Project Manager, the designer GUI.
"""
from __future__ import annotations
import os
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, simpledialog

from pipeline3 import app
import pipeline3.phases  # noqa: F401  (side-effect: registers every phase into the registry)
from pipeline3.context import PipelineContext
from pipeline3.core import config
from pipeline3.io import render
from pipeline3.registry import registry
from pipeline3.gui import fonts, theme, darktitle, phasebar, logview, excel, files
from pipeline3.project import project, state

_ICON = os.path.join(config.APP_ROOT, "assets", "Pipeline3.png")
_APP_NAME = "Pipeline3"
_SESSIONS = {"main": "Broski Session", "designer": "IOList & CEMatrix Validation"}


class App:
    def __init__(self, root: tk.Tk, profile: str = "main", lang: str = "en"):
        self.root = root
        self.profile = profile
        self.lang = lang
        self.reg = registry()
        self.q: queue.Queue = queue.Queue()
        self._run_buttons: list = []
        self._busy = False
        self._ctx: PipelineContext | None = None
        self._logfile = None                       # the "Log to File" run-log handle (None = off)
        self.project_path: str | None = None       # the active project's project.yaml (None = builtin/shared)
        self.params: dict = {}
        self._init_project()                       # auto-reopen the last project, else the shared profile

        self._ui = config.load_app_ui()             # app_config.yaml user_interface: launch settings
        fonts.register()
        self.font_family = fonts.family(root)
        self.dark = (self._ui["theme"] == "dark")
        self.pal = theme.apply_base(root, self.font_family, self.dark)   # sv-ttk + Monaspace default

        root.title(self._session_title())
        root.configure(bg=self.pal["bg"])
        root.geometry(f"{self._ui['width']}x{self._ui['height']}")      # START size only - stays resizable
        root.minsize(900, 560)
        try:
            self._icon = tk.PhotoImage(file=_ICON)
            root.iconphoto(True, self._icon)
        except Exception:  # noqa: BLE001
            pass

        self._build()
        darktitle.apply(root, self.dark)
        if self._ui["log_to_file"]:                 # honor the launch setting (programmatic set doesn't fire)
            self._toggle_logfile()
        root.after(60, self._drain)

    # ---- layout ---------------------------------------------------------- #
    def _build(self):
        self.status = tk.StringVar(value="Ready")
        top = ttk.Frame(self.root, padding=(8, 6, 8, 2))
        top.pack(side="top", fill="x")
        ttk.Label(top, text="PIPELINE3", font=(self.font_family, 13, "bold")).pack(side="left")
        # Project Manager cluster (left): New / Open▾ (recent + Open… + Set root… + Close) + active-project label
        ttk.Button(top, text="New Project", command=self._new_project).pack(side="left", padx=(12, 2))
        self._proj_mb = ttk.Menubutton(top, text="Open Project ▾")
        self._proj_menu = tk.Menu(self._proj_mb, tearoff=False, postcommand=self._build_project_menu)
        self._proj_mb.configure(menu=self._proj_menu)
        self._proj_mb.pack(side="left", padx=2)
        self._proj_label_var = tk.StringVar()
        ttk.Label(top, textvariable=self._proj_label_var).pack(side="left", padx=(10, 0))
        self._update_project_label()
        ttk.Button(top, text="Clear Log", command=self._clear).pack(side="right")
        self._logfile_var = tk.BooleanVar(value=self._ui["log_to_file"])   # launch default from app_config
        ttk.Checkbutton(top, text="Log to File", variable=self._logfile_var,
                        command=self._toggle_logfile).pack(side="right", padx=6)
        ttk.Button(top, text="Open Output", command=lambda: self._startfile(self._out_root())).pack(side="right", padx=6)
        self._theme_btn = ttk.Button(top, text="◐ Theme", command=self._toggle_theme)
        self._theme_btn.pack(side="right", padx=(0, 6))
        self._lang_btn = ttk.Button(top, text=f"Lang: {self.lang.upper()}", command=self._toggle_lang)
        self._lang_btn.pack(side="right", padx=(0, 6))

        self._bar_holder = ttk.Frame(self.root)
        self._bar_holder.pack(side="top", fill="x", padx=4)
        self._build_bar()
        # designer chrome: the two input-file pickers, in their OWN holder (NOT inside self.bar, so the
        # theme/lang _rebuild_bar never orphans them). Shown only for profiles that opt in (input_pickers).
        self._picker_entries: dict = {}
        if self.reg.profile_attr(self.profile, "input_pickers"):
            strip = ttk.Frame(self.root, padding=(8, 2, 8, 0))
            strip.pack(side="top", fill="x")
            self._build_designer_pickers(strip)
        ttk.Separator(self.root, orient="horizontal").pack(side="top", fill="x", pady=(4, 0))

        self.nb = nb = ttk.Notebook(self.root)
        nb.pack(side="top", fill="both", expand=True, padx=4, pady=4)
        log_tab = ttk.Frame(nb)
        nb.add(log_tab, text="Log")
        self.log = logview.LogView(log_tab, self.pal, self.font_family, on_link=self._open_link)
        self.log.pack(fill="both", expand=True)
        files_tab = ttk.Frame(nb)
        nb.add(files_tab, text="Files")
        self.files = files.FilesPanel(files_tab, self.pal, self.font_family, self._file_sections(),
                                      on_status=lambda m: self.status.set(m), dark=self.dark)
        self.files.pack(fill="both", expand=True)

        bottom = ttk.Frame(self.root, padding=(8, 2))
        bottom.pack(side="bottom", fill="x")
        ttk.Label(bottom, textvariable=self.status).pack(side="left")
        self.progress = ttk.Progressbar(bottom, mode="indeterminate", length=160)
        self.progress.pack(side="right")

        self._banner()

    def _session_title(self) -> str:
        """'Pipeline3 - <session> (<profile>)[ - <project>]' - app name, named session, active project."""
        base = f"{_APP_NAME} - {_SESSIONS.get(self.profile, self.profile)} ({self.profile})"
        return f"{base} - {project.project_name(self.project_path)}" if self.project_path else base

    def _banner(self):
        self.log.append(self._session_title(), "SECTION")
        self.log.append(f"font: {self.font_family}   theme: {'dark' if self.dark else 'light'}   "
                        f"lang: {self.lang}   profile: {self.profile}   "
                        f"phases: {', '.join(str(p.number) for p in self.reg.presentation_order(self.profile))}")
        proj = project.project_name(self.project_path) if self.project_path else "(none -> Shared/OutputTree)"
        self.log.append(f"project: {proj}   output: {self._out_root()}")

    def _build_bar(self):
        self._run_buttons = []
        run, phases = phasebar.build_spec(
            self.reg, self.lang,
            run_cb=lambda: self._start_all,
            phase_cb=lambda ph: (lambda n=ph.number: self._start(n)),
            button_cb=self._button_cb,
            include_run=(self.profile == "main"), profile=self.profile)
        self.bar = phasebar.PhaseBar(self._bar_holder, run, phases, self._run_buttons,
                                     dark=self.dark, bg=self.pal["bg"], font=self.font_family, padding=(6, 2))
        self.bar.pack(fill="x")

    def _rebuild_bar(self):
        try:
            self.bar.destroy()
        except Exception:  # noqa: BLE001
            pass
        self._build_bar()

    # ---- toggles --------------------------------------------------------- #
    def _toggle_lang(self):
        self.lang = "it" if self.lang == "en" else "en"
        self._lang_btn.configure(text=f"Lang: {self.lang.upper()}")
        self._rebuild_bar()
        self.status.set(f"language: {self.lang}")

    def _toggle_theme(self):
        self.dark = not self.dark
        self.pal = theme.apply_base(self.root, self.font_family, self.dark)
        self.root.configure(bg=self.pal["bg"])
        self.log.retheme(self.pal)
        if hasattr(self, "files"):
            self.files.retheme(self.pal, self.dark)
        self._rebuild_bar()
        darktitle.apply(self.root, self.dark)
        self.status.set(f"theme: {'dark' if self.dark else 'light'}")

    # ---- project manager ------------------------------------------------- #
    def _init_project(self):
        """Resolve the active project at launch: auto-reopen the last-opened one (your choice), else the
        builtin profile (-> Shared/OutputTree, the Open2App/Openn3 import contract)."""
        last = state.last_opened()
        if last:
            try:
                project.open_project(last)
                config.use_project(project.project_dir(last))
                self.params = config.load_params(last)
                self.project_path = last
                return
            except Exception:  # noqa: BLE001  (vanished / corrupt -> fall back to builtin)
                pass
        config.use_builtin()
        self.params = config.load_params(config.profile_params_file(self.profile))

    def _update_project_label(self):
        name = project.project_name(self.project_path) if self.project_path else "(none — shared output)"
        self._proj_label_var.set(f"Project: {name}")

    def _build_project_menu(self):
        """(Re)build the Open-Project dropdown on post so the recent list stays current."""
        m = self._proj_menu
        m.delete(0, "end")
        recents = [p for p in state.recent_projects() if p != self.project_path]
        for path in recents:
            m.add_command(label=f"  {project.project_name(path)}", command=lambda p=path: self._open_project(p))
        if recents:
            m.add_separator()
        m.add_command(label="Open…", command=lambda: self._open_project(None))
        m.add_command(label="Set projects root…", command=self._set_projects_root)
        if self.project_path:
            m.add_separator()
            m.add_command(label="Re-select IOList…", command=lambda: self._reselect_input("io_list"))
            m.add_command(label="Re-select CEMatrix…", command=lambda: self._reselect_input("ce"))
        m.add_separator()
        m.add_command(label="Close project", command=lambda: self._switch_project(None),
                      state=("normal" if self.project_path else "disabled"))

    def _switch_project(self, path):
        """Activate `path` (a project.yaml) or, with None, close to the builtin shared profile. Rebuilds
        the ctx + files tree + title; resets the log + the run-log handle (it pointed at the old output)."""
        if self._busy:
            self.status.set("busy — finish the run first")
            return
        if path:
            config.use_project(project.project_dir(path))
            self.params = config.load_params(path)
            self.project_path = path
            state.push_recent(path)
        else:
            config.use_builtin()
            self.params = config.load_params(config.profile_params_file(self.profile))
            self.project_path = None
            state.clear_last_opened()
        self._ctx = None                                   # rebuild on the next run with the new params
        if self._logfile is not None:                      # the old handle points at the old output root
            self._logfile_var.set(False)
            self._toggle_logfile()
        self.log.clear()
        self.files.sections = self._file_sections()
        self.files.refresh()
        self.root.title(self._session_title())
        self._update_project_label()
        self._refresh_designer_pickers()
        self._banner()
        self.status.set(f"project: {project.project_name(path)}" if path else "closed project — shared output")

    def _new_project(self):
        if self._busy:
            return
        name = simpledialog.askstring("New Project", "Project name:", parent=self.root)
        if not name or not name.strip():
            return
        folder = os.path.join(state.projects_root(), name.strip())
        if os.path.exists(folder):
            self.status.set(f"already exists: {os.path.basename(folder)}")
            return
        try:
            if self.reg.profile_attr(self.profile, "input_pickers"):
                # picker-profile (designer): seed from the profile base (designer_params), keep its source
                # paths, copy them in - NO file dialogs; the user (re)picks via the persistent pickers.
                path = project.new_project(folder, base_params=config.profile_params_file(self.profile),
                                           keep_inputs=True)
                project.save_project(project.load_doc(path), path, copy_inputs=True)
            else:
                path = project.new_project(folder)
                doc = project.load_doc(path)
                io = filedialog.askopenfilename(parent=self.root, title="I/O List workbook (optional)",
                                                filetypes=[("Excel", "*.xlsx *.xlsm"), ("All files", "*.*")])
                ce = filedialog.askopenfilename(parent=self.root, title="Cause & Effect Matrix (optional)",
                                                filetypes=[("Excel", "*.xlsx *.xlsm"), ("All files", "*.*")])
                if io:
                    doc.setdefault("io_list", {})["path"] = io
                if ce:
                    doc.setdefault("ce", {})["path"] = ce
                project.save_project(doc, path, copy_inputs=True)
        except Exception as e:  # noqa: BLE001
            self.status.set(f"new project failed: {e}")
            return
        self._switch_project(path)

    def _open_project(self, path=None):
        if path is None:
            folder = filedialog.askdirectory(parent=self.root, title="Open Project (pick its folder)",
                                             initialdir=state.projects_root())
            if not folder:
                return
            path = project.project_yaml(folder)
        try:
            project.open_project(path)
        except FileNotFoundError:
            self.status.set("no project.yaml in that folder")
            return
        self._switch_project(path)

    def _set_projects_root(self):
        folder = filedialog.askdirectory(parent=self.root, title="Projects root", initialdir=state.projects_root())
        if folder:
            state.set_projects_root(folder)
            self.status.set(f"projects root: {folder}")

    def _reselect_input(self, key: str):
        """Re-pick the ACTIVE project's I/O List (key='io_list') or C&E (key='ce') workbook: copy it into
        the project's Input/ + repoint project.yaml, then refresh the active params / ctx / files tree."""
        if not self.project_path:
            self.status.set("open a project first")
            return
        if self._busy:
            self.status.set("busy — finish the run first")
            return
        label = "I/O List" if key == "io_list" else "Cause & Effect Matrix"
        picked = filedialog.askopenfilename(parent=self.root, title=f"Re-select {label}",
                                            filetypes=[("Excel", "*.xlsx *.xlsm"), ("All files", "*.*")])
        if not picked:
            return
        try:
            doc = project.load_doc(self.project_path)
            doc.setdefault(key, {})["path"] = picked
            project.save_project(doc, self.project_path, copy_inputs=True)   # copies into Input/, repoints
            self.params = config.load_params(self.project_path)
        except Exception as e:  # noqa: BLE001
            self.status.set(f"re-select failed: {e}")
            return
        self._ctx = None                                   # rebuild on the next run with the new input
        self.files.sections = self._file_sections()
        self.files.refresh()
        self.status.set(f"{label} -> Input/{os.path.basename(picked)}")

    # ---- designer input pickers ----------------------------------------- #
    def _build_designer_pickers(self, parent):
        """The two input workbooks (I/O List + C&E) as readonly path fields + Browse buttons (designer
        chrome beside the ph100 bar). A pick updates the active project's `source` (re-copied into Input/
        on save + on every run) or, with no project, the in-memory params path."""
        for key, caption in (("io_list", "I/O List"), ("ce", "C&E Matrix")):
            row = ttk.Frame(parent)
            row.pack(side="top", fill="x", pady=1)
            ttk.Label(row, text=f"{caption}:", width=11).pack(side="left")
            ent = ttk.Entry(row)
            ent.pack(side="left", fill="x", expand=True, padx=(0, 6))
            ent.insert(0, self._source_path_for(key))      # gotcha: insert THEN readonly; keep the ref
            ent.configure(state="readonly")
            self._picker_entries[key] = ent
            ttk.Button(row, text="Browse…", command=lambda k=key: self._pick_source(k)).pack(side="left")

    def _source_path_for(self, key: str) -> str:
        """The ORIGINAL source workbook for a picker field - the `source` sub-key (the live file), else
        the resolved path. (load_params preserves `source`; `path` may point at the Input/ copy.)"""
        node = self.params.get(key) or {}
        return node.get("source") or node.get("path") or ""

    def _set_picker_text(self, key: str, text: str):
        ent = self._picker_entries.get(key)
        if ent is None:
            return
        ent.configure(state="normal")
        ent.delete(0, "end")
        ent.insert(0, text)
        ent.configure(state="readonly")

    def _refresh_designer_pickers(self):
        for key in self._picker_entries:
            self._set_picker_text(key, self._source_path_for(key))

    def _pick_source(self, key: str):
        if self._busy:
            self.status.set("busy — finish the run first")
            return
        label = "I/O List" if key == "io_list" else "C&E Matrix"
        picked = filedialog.askopenfilename(parent=self.root, title=f"Select {label}",
                                            filetypes=[("Excel", "*.xlsx *.xlsm"), ("All files", "*.*")])
        if not picked:
            return
        try:
            if self.project_path:
                doc = project.load_doc(self.project_path)
                node = doc.setdefault(key, {})
                node["path"] = picked
                node["source"] = picked                    # the live file; copied into Input/ now + every run
                project.save_project(doc, self.project_path, copy_inputs=True)
                self.params = config.load_params(self.project_path)
            else:                                          # no project: validate the picked source directly
                node = self.params.setdefault(key, {})
                node["path"] = picked
                node["source"] = picked
        except Exception as e:  # noqa: BLE001
            self.status.set(f"select failed: {e}")
            return
        self._ctx = None
        self._set_picker_text(key, self._source_path_for(key))
        if hasattr(self, "files"):
            self.files.sections = self._file_sections()
            self.files.refresh()
        self.status.set(f"{label} source: {os.path.basename(picked)}")

    # ---- button wiring (from the registry) ------------------------------- #
    def _button_cb(self, button, phase):
        if button.kind == "disabled":
            return None
        if button.kind == "open":
            key = button.command_key.split(":", 1)[1] if ":" in button.command_key else ""
            return lambda k=key: self._open_artifact(k)
        if button.kind == "special":
            return lambda b=button: self.status.set(f"{button.command_key}: not wired yet")
        if button.number is not None:                  # action -> run the (sub-)phase number
            return lambda n=button.number: self._start(n)
        return None

    # ---- worker run ------------------------------------------------------ #
    def _ensure_ctx(self) -> PipelineContext:
        if self._ctx is None:
            ctx = PipelineContext.create(profile=self.profile, params=self.params)
            ctx.on_progress = lambda m: self.q.put(("status", m))   # live sub-step text -> status bar
            ctx.on_phase_log = self._phase_log                       # each phase's block -> log pane (+ file)
            self._ctx = ctx
        return self._ctx

    def _phase_log(self, entries):
        """A completed (sub-)phase's LogEntry slice (worker thread): render it into the log pane as one
        structured block, and tee it to the run-log file when 'Log to File' is on."""
        self.q.put(("records", render.render_records(entries)))
        f = self._logfile
        if f is not None:
            try:
                f.write(render.render_text(entries) + "\n")
                f.flush()
            except Exception:  # noqa: BLE001
                pass

    def _out_root(self) -> str:
        try:
            return self._ensure_ctx().out_root
        except Exception:  # noqa: BLE001
            return config.output_root(self.params)

    def _start(self, number: int):
        self._run(lambda ctx: self._run_number(ctx, number), f"running {number} ...")

    def _start_all(self):
        def work(ctx):
            ctx.completed.clear()                      # a fresh full run each time "Run Pipeline" is pressed
            app.run_all(ctx)
        self._run(work, "running the whole pipeline ...")

    def _run(self, work, status: str):
        if self._busy:
            return
        self.q.put(("busy", True))
        self.q.put(("status", status))

        def job():
            try:
                ctx = self._ensure_ctx()
                work(ctx)                               # each phase renders its own block via ctx.on_phase_log
                self.q.put(("status", "Ready"))
            except Exception as e:  # noqa: BLE001
                self.q.put(("log", f"[ERROR] {type(e).__name__}: {e}"))
                self.q.put(("status", "error - see the log"))
            finally:
                self.q.put(("busy", False))
        threading.Thread(target=job, daemon=True).start()

    def _run_number(self, ctx, number: int):
        """Run a whole phase (hundreds) or one sub-phase (its prerequisites first). Clicking a phase
        RE-RUNS it (prereqs stay memoized) so its log refreshes each time."""
        if self.reg.profile_attr(self.profile, "live_source") and number // 100 == 1:
            self._refresh_designer_inputs(ctx)             # re-copy the live source before any ph1x0 run
        if number % 100 == 0:
            ctx.completed.discard(number)
            app.run_phase(ctx, number)
            return
        parent = (number // 100) * 100
        ph = self.reg.get(parent)
        for req in ph.requires:
            app.run_phase(ctx, req)
        sub = next((s for s in (ph.sub_phases or []) if s.number == number), None)
        if sub is None or sub.run is None:
            self.q.put(("log", f"{number}: not implemented"))
            return
        app.run_subphase(ctx, sub)

    def _refresh_designer_inputs(self, ctx):
        """'Live source' profiles (designer): before each ph1x0 run, re-copy the project's input `source`
        files onto their Input/ copies (so validation reads the latest saved bytes), then invalidate the
        staged rows + the 300/100 memoization so the next run_phase re-stages off the fresh bytes. With no
        project open, validation already reads the picked source directly - we only re-stage."""
        try:
            if self.project_path:
                doc = project.load_doc(self.project_path)
                names = project.refresh_inputs(doc, project.project_dir(self.project_path))
                if names:
                    self.q.put(("status", f"refreshed source: {', '.join(names)}"))
        except Exception as e:  # noqa: BLE001
            self.q.put(("log", f"[WARN] could not refresh source: {e}"))
        ctx.rows = None                                    # re-stage this run (p300 memoizes on ctx.rows)
        ctx.populated_path = ""
        ctx.completed.discard(300)
        ctx.completed.discard(100)

    # ---- queue drain (main thread) --------------------------------------- #
    def _drain(self):
        try:
            while True:
                ev = self.q.get_nowait()
                if ev[0] == "log":
                    self.log.append(ev[1])
                elif ev[0] == "records":
                    self.log.append_records(ev[1], self._error_csv_path(), self._resolve_doc)
                elif ev[0] == "busy":
                    self._set_busy(ev[1])
                elif ev[0] == "status":
                    self.status.set(ev[1])
        except queue.Empty:
            pass
        self.root.after(60, self._drain)

    def _set_busy(self, busy: bool):
        self._busy = busy
        for b in self._run_buttons:
            try:
                b.configure(state="disabled" if busy else "normal")
            except tk.TclError:
                pass
        if busy:
            self.progress.start(12)
        else:
            self.progress.stop()

    # ---- opens / links --------------------------------------------------- #
    def _clear(self):
        self.log.clear()

    def _toggle_logfile(self):
        """The 'Log to File' checkbox: open (truncate) the run-log when turned on, close it when off.
        _phase_log tees each rendered phase block to this handle while it is open."""
        if self._logfile is not None:
            try:
                self._logfile.close()
            except Exception:  # noqa: BLE001
                pass
            self._logfile = None
        if self._logfile_var.get():
            path = config.out_path(self._out_root(), "run_log") + ".txt"
            try:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                self._logfile = open(path, "w", encoding="utf-8")
                self.status.set(f"logging to {os.path.basename(path)}")
            except Exception as e:  # noqa: BLE001
                self._logfile_var.set(False)
                self.status.set(f"could not open log file: {e}")
        else:
            self.status.set("file logging off")

    def _io_list_path(self) -> str:
        return (self.params.get("io_list") or {}).get("path", "")

    def _file_sections(self):
        """The 3 Files-tree sections: project configuration / user editable files / bare outputs - all
        under the ACTIVE config (a project's, or the app's when none is open)."""
        io = (self.params.get("io_list") or {}).get("path", "")
        ce = (self.params.get("ce") or {}).get("path", "")
        user = [p for p in (io, ce) if p]
        uin = config.user_input_dir()
        if os.path.isdir(uin):
            user.append(uin)
        return [("Project configuration", [config.config_project_dir()]),
                ("User editable files", user),
                ("Bare output files", [self._out_root()])]

    def _doc_path_map(self) -> dict:
        """{workbook basename -> abspath} for the docs the log links into (I/O List + C&E), with an
        os.path.normcase alias so a case-differing basename still resolves on Windows."""
        io = self._ctx.io_list_path() if self._ctx is not None else self._io_list_path()
        ce = (self.params.get("ce") or {}).get("path", "")
        m = {}
        for p in (io, ce):
            if p:
                b = os.path.basename(p)
                m[b] = p
                m[os.path.normcase(b)] = p
        return m

    def _resolve_doc(self, doc: str) -> str:
        """The workbook path for a link's `doc` basename; falls back to the I/O List."""
        m = self._doc_path_map()
        return m.get(doc) or m.get(os.path.normcase(doc or "")) or self._io_list_path()

    def _error_csv_path(self) -> str:
        return os.path.join(config.user_input_dir(), "error_management.csv")

    def _open_link(self, doc: str, sheet: str, cell: str):
        """A Sheet!Cell link in the log -> open ITS workbook (I/O List or C&E) in Excel at that cell
        (worker thread, COM); `doc` is the workbook basename the LogEntry carried."""
        path = self._resolve_doc(doc)
        self.status.set(f"opening Excel at {sheet}!{cell} ...")

        def job():
            ok, msg = excel.goto(path, sheet, cell)
            self.q.put(("status", msg))
        threading.Thread(target=job, daemon=True).start()

    def _startfile(self, path: str):
        if path and os.path.exists(path):
            try:
                os.startfile(path)  # type: ignore[attr-defined]
                self.status.set(f"opened {os.path.basename(path) or path}")
                return
            except Exception as e:  # noqa: BLE001
                self.status.set(str(e))
                return
        self.status.set("not found (run the phase first)" if path else "nothing to open")

    def _open_artifact(self, key: str):
        params = self.params
        if key == "io_list":
            return self._startfile((params.get("io_list") or {}).get("path", ""))
        if key == "ce":
            return self._startfile((params.get("ce") or {}).get("path", ""))
        fixed = {"signal_types": os.path.join(config.input_docs_dir(), "signal_types.csv"),
                 "fill_config": config.input_docs_dir(),
                 "diag_config": config.diagnosis_dir(),
                 "error_management": os.path.join(config.user_input_dir(), "error_management.csv")}
        if key in fixed:
            return self._startfile(fixed[key])
        if key in config.OUTPUT_PATHS:
            base = config.out_path(self._out_root(), key)
            for cand in (base, base + ".txt", base + ".csv"):     # report bases carry an extension
                if os.path.exists(cand):
                    return self._startfile(cand)
            return self._startfile(base)
        self.status.set(f"open '{key}': not wired yet")


def main(profile: str | None = None, lang: str = "en"):
    """Launch the operator window. The profile defaults to config_project/app_config.yaml's `profile`
    (so launch_gui.py stays argument-free); an unknown profile falls back to 'main'. ONE GUI, one exe -
    the profile is a shipped config value, not a separate build."""
    if profile is None:
        profile = config.load_app_profile()
    reg = registry()
    if not reg.has_profile(profile):
        print(f"app_config.yaml: unknown profile {profile!r} -> falling back to 'main'")
        profile = "main"
    root = tk.Tk()
    App(root, profile=profile, lang=lang)
    root.mainloop()


if __name__ == "__main__":
    main()
