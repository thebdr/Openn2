"""The users' GUI (user 2026-10-25: "sycon5app needs a basic gui for the users. buttons to retrieve the workspace data
and a log viewer"): one window - the workspace (a PRODUCTION folder) and its cards as `workspace.scan` reads them,
the buttons of the steps (the handoff export from an I/O List, the build of a card, its resume, its verification,
the BusField), and the log viewer: the output of the running step live, or any log / report of the workspace,
coloured by level like PL5's log pane. A step runs as a subprocess (the same scripts `scripts/build_production.sh`
runs, its output written to the same `_PL_Logs` file) - never in this process: SYCON.net is driven from the script,
and while it runs the desktop must be left alone, which the banner says. Stop sends the script a CTRL_BREAK (its
`finally` closes SYCON.net) and terminates it when that cannot arrive (no console: launched with pythonw) or is not
answered in time.
Run:  python launch_gui.py [<PRODUCTION folder>]   (the repo venv; the last workspace is remembered)."""
import ctypes
import json
import os
import queue
import signal
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, ttk

from . import workspace as ws

# PL5's dark workbench palette (Pipeline5App/pipeline5/workbench/theme.py) so the two apps look alike
BG, FG, PANEL, FIELD, MUTED = "#1e1e1e", "#dfe6e9", "#2d3436", "#262b2e", "#8f9ba2"
RUN_BG, STOP_BG, BANNER_BG, BANNER_FG, SELECT_BG = "#e84393", "#636e72", "#fdcb6e", "#1e272e", "#3b4f6b"
LOG_COLORS = {"RSLT": ("#00d2d3", True), "FAIL": ("#ff6b6b", True), "ERRR": ("#e17055", True),
              "WARN": ("#fdcb6e", False), "PASS": ("#55efc4", False), "NOTE": ("#b2bec3", False), "INFO": (FG, False)}
UI_FONT, BOLD_FONT, MONO_FONT = ("Segoe UI", 10), ("Segoe UI", 10, "bold"), ("Consolas", 10)
FILTERABLE = ("PASS", "NOTE", "INFO")               # the levels the viewer can hide; the rest always shows
RUN_OUTPUT = "run output"
SETTINGS = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "Sycon5App", "gui.json")
STOP_GRACE_S = 120.0                                # CTRL_BREAK answered (SYCON.net closed) before a terminate
MAX_RUN_LINES = 20000
COLUMNS = (("card", "Card", 44), ("project", "Project", 120), ("controller", "Controller", 180), ("stations", "Stations", 62),
           ("modules", "Modules", 62), ("generated", "Handoff (UTC)", 130), ("built", "Project saved", 116),
           ("verification", "Verification", 180), ("verified", "Verified", 116), ("exports", "Exports", 56), ("status", "Status", 180))


def when(t):
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(t)) if t else ""


def has_console():
    return bool(ctypes.windll.kernel32.GetConsoleWindow()) if os.name == "nt" else True


def dark_title_bar(root):
    """The window's title bar dark too (DWMWA_USE_IMMERSIVE_DARK_MODE, as PL5's darktitle does); best effort."""
    if os.name != "nt":
        return
    try:
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        value = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(value), ctypes.sizeof(value))
    except (AttributeError, OSError):
        pass


def load_settings(path=SETTINGS):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_settings(data, path=SETTINGS):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1)
    except OSError:
        pass


class Runner:
    """One step at a time as a subprocess; its lines reach the GUI thread through a queue (`poll` from `after`)."""

    def __init__(self):
        self.proc = None
        self.command = None
        self.lines = queue.Queue()
        self.stopped = False
        self._sink = None
        self._stop_at = 0.0

    @property
    def running(self):
        return self.proc is not None

    def start(self, command):
        os.makedirs(os.path.dirname(command.log), exist_ok=True)
        sink = open(command.log, "w", encoding="utf-8")                  # one file per run, as the bash script writes it
        flags = subprocess.CREATE_NEW_PROCESS_GROUP                      # so a CTRL_BREAK reaches this child alone
        if not has_console():
            flags |= subprocess.CREATE_NO_WINDOW
        try:
            proc = subprocess.Popen(command.argv, cwd=command.cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                                    bufsize=1, creationflags=flags)
        except OSError:
            sink.close()
            raise
        self.proc, self.command, self._sink, self.stopped, self._stop_at = proc, command, sink, False, 0.0
        threading.Thread(target=self._read, args=(proc,), daemon=True).start()

    def _read(self, proc):
        for line in proc.stdout:
            self.lines.put(line.rstrip("\r\n"))
        proc.stdout.close()
        self.lines.put(None)                                             # end of output

    def stop(self):
        """CTRL_BREAK to the step (build_from_handoff.py turns it into a KeyboardInterrupt: its `finally` closes
        SYCON.net), a terminate after STOP_GRACE_S; a terminate at once when the signal cannot arrive (the GUI has no
        console - launched with pythonw - so the child got its own hidden one; probed 2026-10-25)."""
        if not self.proc:
            return
        self.stopped = True
        if has_console():
            try:
                self.proc.send_signal(signal.CTRL_BREAK_EVENT)
                self._stop_at = time.time() + STOP_GRACE_S
                return
            except OSError:
                pass
        self.proc.terminate()

    def poll(self):
        """(new lines, exit code or None while running); the lines also go to the log file."""
        out, done = [], False
        while True:
            try:
                item = self.lines.get_nowait()
            except queue.Empty:
                break
            if item is None:
                done = True
                break
            out.append(item)
        if out and self._sink:
            self._sink.write("\n".join(out) + "\n")
            self._sink.flush()
        if self.proc and self._stop_at and time.time() > self._stop_at and self.proc.poll() is None:
            self.proc.terminate()
            self._stop_at = 0.0
        code = None
        if done:
            code = self.proc.wait()
            self._sink.close()
            self._sink, self.proc = None, None
        return out, code


class App:
    def __init__(self, root, workspace_root=None, settings_path=SETTINGS):
        self.root = root
        self.settings_path = settings_path
        self.settings = load_settings(settings_path)
        self.workspace = None
        self.runner = Runner()
        self.pending = []                                                # the commands queued after the running one
        self.run_lines = []                                              # the run output the viewer shows
        self._log_paths = {}
        root.title("Sycon5App - SYCON.net projects")
        root.geometry(self.settings.get("geometry", "1280x800"))
        root.minsize(900, 560)
        root.configure(background=BG)
        self._style()
        self._build()
        root.update_idletasks()
        dark_title_bar(root)
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        path = workspace_root or self.settings.get("workspace") or ""
        if path and os.path.isdir(path):
            self.open_workspace(path)
        else:
            self.say("INFO", "Open a workspace: the PRODUCTION folder PL5 wrote (HilscherIOCard<n>/SyconNetProjectInterface per card).")
        self._enable()
        root.after(150, self._tick)

    # ---- the look ---------------------------------------------------------------------------------------------- #
    def _style(self):
        s = ttk.Style(self.root)
        s.theme_use("clam")
        s.configure(".", background=BG, foreground=FG, fieldbackground=FIELD, font=UI_FONT, borderwidth=0)
        s.configure("TFrame", background=BG)
        s.configure("TLabel", background=BG, foreground=FG)
        s.configure("Muted.TLabel", background=BG, foreground=MUTED)
        s.configure("Banner.TLabel", background=BANNER_BG, foreground=BANNER_FG, font=BOLD_FONT, padding=6)
        s.configure("TButton", background=PANEL, foreground=FG, padding=(10, 4), relief="flat")
        s.map("TButton", background=[("active", "#3d4548"), ("disabled", "#2a2f31")], foreground=[("disabled", "#6b7579")])
        s.configure("Run.TButton", background=RUN_BG, foreground="#ffffff", font=BOLD_FONT)
        s.map("Run.TButton", background=[("active", "#f06ab0"), ("disabled", "#5a3348")], foreground=[("disabled", "#b89aa7")])
        s.configure("Stop.TButton", background=STOP_BG, foreground="#ffffff")
        s.map("Stop.TButton", background=[("active", "#7d8a8e"), ("disabled", "#2a2f31")], foreground=[("disabled", "#6b7579")])
        s.configure("TEntry", fieldbackground=FIELD, foreground=FG, insertcolor=FG)
        s.map("TEntry", fieldbackground=[("readonly", FIELD)], foreground=[("readonly", FG)])
        s.configure("TCombobox", fieldbackground=FIELD, foreground=FG, arrowcolor=FG, background=PANEL)
        s.map("TCombobox", fieldbackground=[("readonly", FIELD)], foreground=[("readonly", FG)])
        s.configure("TCheckbutton", background=BG, foreground=FG)
        s.map("TCheckbutton", background=[("active", BG)])
        s.configure("Treeview", background=FIELD, fieldbackground=FIELD, foreground=FG, rowheight=24, font=UI_FONT)
        s.configure("Treeview.Heading", background=PANEL, foreground=FG, font=BOLD_FONT, relief="flat")
        s.map("Treeview", background=[("selected", SELECT_BG)], foreground=[("selected", "#ffffff")])
        for orient in ("Vertical", "Horizontal"):
            s.configure("%s.TScrollbar" % orient, background=PANEL, troughcolor=BG, arrowcolor=FG)
        s.configure("TSeparator", background=PANEL)
        self.root.option_add("*TCombobox*Listbox.background", FIELD)
        self.root.option_add("*TCombobox*Listbox.foreground", FG)
        self.root.option_add("*TCombobox*Listbox.font", UI_FONT)

    def _build(self):
        """Rows: 0 the workspace, 1 the cards, 2 the actions, 3 the banner (hidden while idle), 4 the log bar, 5 the pane."""
        r = self.root
        r.grid_columnconfigure(0, weight=1)
        r.grid_rowconfigure(5, weight=1)
        top = ttk.Frame(r, padding=(8, 8, 8, 4))
        top.grid(row=0, column=0, sticky="ew")
        ttk.Label(top, text="Workspace").pack(side="left")
        self.path_var = tk.StringVar()
        ttk.Entry(top, textvariable=self.path_var, state="readonly").pack(side="left", fill="x", expand=True, padx=8)
        self.b_open = ttk.Button(top, text="Open...", command=self.choose_workspace)
        self.b_open.pack(side="left")
        self.b_reload = ttk.Button(top, text="Reload", command=self.reload)
        self.b_reload.pack(side="left", padx=(4, 0))
        self.b_explorer = ttk.Button(top, text="Explorer", command=lambda: self.open_folder(self.workspace and self.workspace.root))
        self.b_explorer.pack(side="left", padx=(4, 0))
        ttk.Separator(top, orient="vertical").pack(side="left", fill="y", padx=10)
        self.b_export = ttk.Button(top, text="I/O List > handoff...", command=self.export_handoff)
        self.b_export.pack(side="left")

        mid = ttk.Frame(r, padding=(8, 0, 8, 4))
        mid.grid(row=1, column=0, sticky="ew")
        mid.grid_columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(mid, columns=[c[0] for c in COLUMNS], show="headings", height=6, selectmode="browse")
        for key, title, width in COLUMNS:
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width, minwidth=40, anchor="w", stretch=(key in ("controller", "status")))
        vs = ttk.Scrollbar(mid, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vs.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vs.grid(row=0, column=1, sticky="ns")
        self.tree.tag_configure("ok", foreground=LOG_COLORS["PASS"][0])
        self.tree.tag_configure("bad", foreground=LOG_COLORS["FAIL"][0])
        self.tree.tag_configure("todo", foreground=LOG_COLORS["WARN"][0])
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._enable())
        self.tree.bind("<Double-1>", lambda _e: self.open_folder(self.selected_card() and self.selected_card().folder))

        act = ttk.Frame(r, padding=(8, 0, 8, 4))
        act.grid(row=2, column=0, sticky="ew")
        self.b_build = ttk.Button(act, text="Build card", style="Run.TButton", command=lambda: self.build_selected(False))
        self.b_resume = ttk.Button(act, text="Resume build", command=lambda: self.build_selected(True))
        self.b_update = ttk.Button(act, text="Update card", command=lambda: self.build_selected(update=True))
        self.b_verify = ttk.Button(act, text="Verify card", command=self.verify_selected)
        self.b_folder = ttk.Button(act, text="Card folder", command=lambda: self.open_folder(self.selected_card() and self.selected_card().folder))
        for b in (self.b_build, self.b_resume, self.b_update, self.b_verify, self.b_folder):
            b.pack(side="left", padx=(0, 4))
        ttk.Separator(act, orient="vertical").pack(side="left", fill="y", padx=6)
        self.b_all = ttk.Button(act, text="Build all cards + BusField", style="Run.TButton", command=self.build_all)
        self.b_all.pack(side="left", padx=(0, 4))
        self.b_busfield = ttk.Button(act, text="BusField", command=self.busfield)
        self.b_busfield.pack(side="left")
        self.b_stop = ttk.Button(act, text="Stop", style="Stop.TButton", command=self.stop)
        self.b_stop.pack(side="right")

        self.banner_var = tk.StringVar()
        self.banner = ttk.Label(r, textvariable=self.banner_var, style="Banner.TLabel", anchor="w")
        self.banner.grid(row=3, column=0, sticky="ew", padx=8, pady=(0, 4))
        self.banner.grid_remove()

        bar = ttk.Frame(r, padding=(8, 2, 8, 2))
        bar.grid(row=4, column=0, sticky="ew")
        ttk.Label(bar, text="Log").pack(side="left")
        self.log_var = tk.StringVar(value=RUN_OUTPUT)
        self.log_box = ttk.Combobox(bar, textvariable=self.log_var, state="readonly", width=60)
        self.log_box.pack(side="left", padx=8)
        self.log_box.bind("<<ComboboxSelected>>", lambda _e: self.show_log())
        ttk.Button(bar, text="Reload", command=self.show_log).pack(side="left")
        ttk.Button(bar, text="Clear", command=self.clear_log).pack(side="left", padx=(4, 0))
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=10)
        ttk.Label(bar, text="Show", style="Muted.TLabel").pack(side="left")
        self.level_vars = {}
        shown = set(self.settings.get("levels", list(FILTERABLE)))
        for level in FILTERABLE:
            var = tk.BooleanVar(value=level in shown)
            self.level_vars[level] = var
            ttk.Checkbutton(bar, text=level, variable=var, command=self._apply_levels).pack(side="left", padx=(6, 0))
        self.follow_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text="Follow", variable=self.follow_var).pack(side="right")
        self.count_var = tk.StringVar()
        ttk.Label(bar, textvariable=self.count_var, style="Muted.TLabel").pack(side="right", padx=10)

        logf = ttk.Frame(r, padding=(8, 0, 8, 8))
        logf.grid(row=5, column=0, sticky="nsew")
        logf.grid_rowconfigure(0, weight=1)
        logf.grid_columnconfigure(0, weight=1)
        self.text = tk.Text(logf, wrap="none", state="disabled", background=BG, foreground=FG, insertbackground=FG,
                            font=MONO_FONT, relief="flat", padx=8, pady=6, selectbackground=SELECT_BG)
        tvs = ttk.Scrollbar(logf, orient="vertical", command=self.text.yview)
        ths = ttk.Scrollbar(logf, orient="horizontal", command=self.text.xview)
        self.text.configure(yscrollcommand=tvs.set, xscrollcommand=ths.set)
        self.text.grid(row=0, column=0, sticky="nsew")
        tvs.grid(row=0, column=1, sticky="ns")
        ths.grid(row=1, column=0, sticky="ew")
        for level, (color, bold) in LOG_COLORS.items():
            self.text.tag_configure(level, foreground=color, font=MONO_FONT + (("bold",) if bold else ()))
        self._apply_levels()

    # ---- the workspace ----------------------------------------------------------------------------------------- #
    def choose_workspace(self):
        start = (self.workspace and self.workspace.root) or self.settings.get("workspace") or ""
        path = filedialog.askdirectory(title="The PRODUCTION folder of the project", initialdir=start or None, mustexist=True)
        if path:
            self.open_workspace(os.path.normpath(path))

    def open_workspace(self, path):
        self.settings["workspace"] = path
        save_settings(self.settings, self.settings_path)
        self.path_var.set(path)
        self.reload()

    @staticmethod
    def row_of(c):
        """The table row of a card and its colour tag: green when built, verified after the save, 0 FAIL and every
        export there; red on a FAIL or a handoff problem; yellow for the rest (something still to do)."""
        tag = "todo"
        if c.failed == 0 and c.exports_present == len(ws.EXPORTS) and c.report_time >= c.project_time - 1 and c.project_dir_ok:
            tag = "ok"
        elif c.failed > 0 or c.problems or not c.report_ok or not c.project_dir_ok:
            tag = "bad"
        values = (c.number, c.name if c.project else "", c.controller, c.stations or "", c.modules or "",
                  c.headers.get("generated", "").replace("T", " ").rstrip("Z"), when(c.project_time), c.verdict,
                  when(c.report_time), "%d/%d" % (c.exports_present, len(ws.EXPORTS)), c.status())
        return values, tag

    def reload(self):
        if not self.path_var.get():
            return
        selected = self.selected_card()
        self.workspace = ws.scan(self.path_var.get())
        self.tree.delete(*self.tree.get_children())
        for c in self.workspace.cards:
            values, tag = self.row_of(c)
            self.tree.insert("", "end", iid=str(c.number), values=values, tags=(tag,))
        if selected and self.tree.exists(str(selected.number)):
            self.tree.selection_set(str(selected.number))
        elif self.workspace.cards:
            self.tree.selection_set(str(self.workspace.cards[0].number))
        for p in self.workspace.problems:
            self.say("WARN", p)
        w = self.workspace
        summary = "%d card(s)" % len(w.cards)
        if w.busfield:
            summary += "; BusField %s" % when(w.busfield_time)
        self.say("INFO", "%s  workspace %s: %s" % (time.strftime("%H:%M:%S"), w.root, summary))
        self._fill_log_list()
        self._enable()

    def _fill_log_list(self):
        files = self.workspace.log_files() if self.workspace else []
        self._log_paths = dict(files)
        current = self.log_var.get()
        values = [RUN_OUTPUT] + [label for label, _p in files]
        self.log_box["values"] = values
        if current not in values:
            self.log_var.set(RUN_OUTPUT)
            self.show_log()

    def selected_card(self):
        sel = self.tree.selection()
        if not sel or not self.workspace:
            return None
        return self.workspace.card(int(sel[0]))

    def card_of_log(self, path):
        for c in (self.workspace.cards if self.workspace else []):
            if os.path.normcase(os.path.dirname(path)) == os.path.normcase(c.logs_dir):
                return c
        return None

    def open_folder(self, path):
        if path and os.path.isdir(path):
            os.startfile(path)

    # ---- the steps --------------------------------------------------------------------------------------------- #
    def export_handoff(self):
        if not self.workspace:
            return
        path = filedialog.askopenfilename(title="The I/O List workbook",
                                          filetypes=[("Excel workbook", "*.xlsx *.xlsm"), ("All files", "*.*")])
        if path:
            self.run(ws.export_command(os.path.normpath(path), self.workspace.root))

    def build_selected(self, resume=False, update=False):
        c = self.selected_card()
        if c and c.handoff:
            self.run(ws.build_command(c, resume=resume, update=update))

    def verify_selected(self):
        c = self.selected_card()
        if c and c.handoff and c.project:
            self.run(ws.verify_command(c))

    def busfield(self):
        if self.workspace:
            self.run(ws.busfield_command(self.workspace.root))

    def build_all(self):
        if not self.workspace:
            return
        cmds = [ws.build_command(c) for c in self.workspace.cards if c.handoff and not c.problems]
        if cmds:
            self.run(cmds[0], then=cmds[1:] + [ws.busfield_command(self.workspace.root)])

    def run(self, command, then=(), fresh=True):
        """Start a step (and queue the ones after it); the run output is cleared for a fresh batch."""
        if self.runner.running:
            return False
        self.pending = list(then)
        if fresh:
            self.run_lines = []
            self.log_var.set(RUN_OUTPUT)
            self.clear_log()
        self.say("RSLT", "%s  %s" % (time.strftime("%H:%M:%S"), command.label))
        self.say("INFO", "  " + subprocess.list2cmdline(command.argv))
        self.say("INFO", "  log: " + command.log)
        if command.drives_sycon:
            ws.note_summary(self.workspace.root, command.label)
        try:
            self.runner.start(command)
        except OSError as ex:
            self.say("ERRR", "could not start: %s" % ex)
            self.pending = []
            return False
        self._set_running(command)
        return True

    def stop(self):
        self.pending = []
        if self.runner.running:
            self.say("WARN", "stop requested - the step is asked to close SYCON.net and end (a terminate after %d s)" % STOP_GRACE_S)
            self.runner.stop()

    def _set_running(self, command):
        if command:
            text = "Running: %s" % command.label
            if command.drives_sycon:
                text += "   -   SYCON.net is being driven: leave the mouse and keyboard alone until this banner goes"
            self.banner_var.set(text)
            self.banner.grid()
        else:
            self.banner.grid_remove()
        self._enable()

    def _tick(self):
        lines, code = self.runner.poll()
        for ln in lines:
            self._run_line(ln, ws.level_of(ln))
        if code is not None:
            self._finished(code)
        self.root.after(150, self._tick)

    def _run_line(self, line, level):
        self.run_lines.append((line, level))
        if len(self.run_lines) > MAX_RUN_LINES:
            del self.run_lines[: len(self.run_lines) - MAX_RUN_LINES]
        if self.log_var.get() == RUN_OUTPUT:
            self._append(line, level)

    def _finished(self, code):
        cmd = self.runner.command
        verdict = "exit %d" % code
        if cmd.drives_sycon:
            head, c = "no report", self.card_of_log(cmd.log)
            if c and os.path.exists(c.report_path):
                with open(c.report_path, encoding="utf-8", errors="replace") as f:
                    head = f.readline().strip() or head
            ws.note_summary(self.workspace.root, "%s: %s - %s" % (cmd.label, verdict, head))
        if self.runner.stopped:
            self.say("WARN", "%s stopped (%s). If SYCON.net is still open, close it without saving." % (cmd.label, verdict))
            self.pending = []
        else:
            self.say("RSLT" if code == 0 else "FAIL", "%s  %s: %s" % (time.strftime("%H:%M:%S"), cmd.label, verdict))
        self.reload()
        if self.pending:
            self.run(self.pending[0], then=self.pending[1:], fresh=False)
        else:
            self._set_running(None)

    def _enable(self):
        running = self.runner.running
        c = self.selected_card()
        idle = self.workspace is not None and not running
        buildable = idle and c is not None and bool(c.handoff) and not c.problems
        built = idle and c is not None and bool(c.handoff and c.project) and c.project_dir_ok
        any_handoff = idle and any(x.handoff and not x.problems for x in self.workspace.cards)
        for b, ok in ((self.b_open, not running), (self.b_reload, idle), (self.b_explorer, idle), (self.b_export, idle),
                      (self.b_build, buildable), (self.b_resume, built), (self.b_update, built), (self.b_verify, built), (self.b_folder, c is not None),
                      (self.b_all, any_handoff), (self.b_busfield, idle), (self.b_stop, running)):
            b.state(["!disabled"] if ok else ["disabled"])

    # ---- the log viewer ---------------------------------------------------------------------------------------- #
    def say(self, level, text):
        """A line of the GUI's own into the run output."""
        self._run_line(text, level)

    def _append(self, line, level):
        self.text.configure(state="normal")
        self.text.insert("end", line + "\n", (level,))
        self.text.configure(state="disabled")
        if self.follow_var.get():
            self.text.see("end")
        self._count()

    def clear_log(self):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")
        self._count()

    def show_log(self):
        """The chosen log: the run output (buffered) or a file of the workspace, re-read now."""
        label = self.log_var.get()
        self.clear_log()
        if label == RUN_OUTPUT:
            lines = list(self.run_lines)
        else:
            path = self._log_paths.get(label)
            if not path:
                return
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    lines = [(ln, ws.level_of(ln)) for ln in f.read().splitlines()]
            except OSError as ex:
                self._append("cannot read %s: %s" % (path, ex), "ERRR")
                return
        self.text.configure(state="normal")
        for ln, level in lines:
            self.text.insert("end", ln + "\n", (level,))
        self.text.configure(state="disabled")
        self.text.see("end" if self.follow_var.get() else "1.0")
        self._count()

    def shown_levels(self):
        return {lv for lv, var in self.level_vars.items() if var.get()} | (set(LOG_COLORS) - set(FILTERABLE))

    def _apply_levels(self):
        for level, var in self.level_vars.items():
            self.text.tag_configure(level, elide=not var.get())
        self.settings["levels"] = sorted(self.shown_levels() & set(FILTERABLE))
        self._count()

    def _count(self):
        total = int(self.text.index("end-1c").split(".")[0]) - 1
        self.count_var.set("%d lines" % total)

    def on_close(self):
        if self.runner.running:
            self.stop()
        self.settings["geometry"] = self.root.geometry()
        save_settings(self.settings, self.settings_path)
        self.root.destroy()


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    root = tk.Tk()
    App(root, argv[0] if argv else None)
    root.mainloop()
    return 0
