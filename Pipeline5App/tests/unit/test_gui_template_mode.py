"""The Files tab's template mode (P-012) driven through the REAL widgets - a FilesPanel on an off-screen
Tk root (SKIPPED where no display exists) - plus the Tk-free read-only / project-copy helpers of
files_view. A temp PROJECT carries the rules + templates (tier 1); the hook's Database is a synthetic
one (the Session's loader stubbed) so no staging runs."""
import os
import re
import tempfile

from _harness import run, eq, ok
from pipeline5 import config
from pipeline5.systems import catalog
from pipeline5.truth.database import Database
from pipeline5.truth.table import Table
from pipeline5.workbench import files_view, template_doc
from tkinter import filedialog, messagebox, simpledialog, ttk

SYSTEM = catalog.by_id("siemens_s7_safety")
_SHIPPED = os.path.join(SYSTEM.config_root, "chain_reactions", "templates.yaml")
_TEMPLATES = ("belt: |-\n"
              "  REGION {$tag}\n"
              "  @for $r in signals where $script_type = \"PEC\"\n"
              "    PEC({$r.tag});\n"
              "  @end\n"
              "  END_REGION\n")
_RULES = ("name,fire_when,source_table,condition,action,target,template,comment\n"
          "belts,after_300,signals,,file,gen/{$tag}.scl,belt,\n")


def _project(root, templates=_TEMPLATES):
    rx = os.path.join(root, "config_project", "systems", SYSTEM.id, "chain_reactions")
    os.makedirs(rx)
    os.makedirs(os.path.join(root, "config_project", "shared"))
    with open(os.path.join(root, "config_project", "shared", "project_params.yaml"), "w", encoding="utf-8") as h:
        h.write("project_code: 8X\n")
    with open(os.path.join(rx, "reactions.csv"), "w", encoding="utf-8") as handle:
        handle.write(_RULES)
    if templates is not None:
        with open(os.path.join(rx, "templates.yaml"), "w", encoding="utf-8") as handle:
            handle.write(templates)
    return os.path.join(rx, "templates.yaml")


def _signals():
    table = Table("signals", columns=["uid", "tag", "script_type"], key_columns=["tag"])
    table.add(tag="B1", script_type="BELT")
    table.add(tag="P1", script_type="PEC")
    return Database([table])


_REAL_SESSION = template_doc.Session


def _session(path=None):
    """The real Session, its after_300 Database synthetic (the Session's seam - no staging here)."""
    return _REAL_SESSION(path, hooks={"before_300": None, "after_300": lambda system: _signals()})


def _pump(root, done, timeout: float = 10.0) -> bool:
    """Run the Tk loop until `done()` - the template mode's checks and preview come from its worker."""
    import time
    deadline = time.time() + timeout
    while time.time() < deadline:
        root.update()
        if done():
            return True
        time.sleep(0.02)
    return False


def _tk():
    import gc
    gc.collect()                                             # an earlier test's Tk garbage - freed HERE
    try:
        import tkinter as tk
        root = tk.Tk()
    except Exception as error:  # noqa: BLE001 - no display: the GUI half is skipped, not failed
        print(f"  SKIP  (no Tk display: {error})")
        return None
    root.geometry("1000x700+-3000+-3000")                  # mapped (bbox works) but off-screen
    return root


def _done(root) -> None:
    """End a test's Tk root: destroy it, then wait for its template-builder workers to end (each gets
    its stop at the text's <Destroy>). This suite makes one root per test in ONE process: a worker
    outliving its test could trigger the cyclic GC that frees an old root's LAST Tk object on that
    worker thread - and Tcl aborts ('Tcl_AsyncDelete: async handler deleted by the wrong thread'). The
    App has one root for its life, so it never frees one mid-run."""
    import threading
    root.destroy()
    for thread in threading.enumerate():
        if thread.name == "template-builder":
            thread.join(10)


def _panel(root, project_root):
    from pipeline5.workbench.files_panel import FilesPanel
    section = {"title": "project", "roots": [os.path.join(project_root, "config_project")],
               "include": [re.compile(".*")], "exclude": []}
    panel = FilesPanel(root, sections=[section])
    panel.pack(fill="both", expand=True)
    root.update()
    return panel


def _buttons(widget) -> list:
    """Every ttk button label under `widget` (recursive)."""
    found = [widget.cget("text")] if widget.winfo_class() == "TButton" else []
    for child in widget.winfo_children():
        found += _buttons(child)
    return found


def _problem_rows(mode, needle: str) -> list:
    """The problems list's rows mentioning `needle`."""
    rows = [mode.problems.item(i, "values") for i in mode.problems.get_children()]
    return [values for values in rows if needle in str(values)]


def _tagged(text, tag):
    ranges = text.tag_ranges(tag)
    return [text.get(ranges[i], ranges[i + 1]) for i in range(0, len(ranges), 2)]


class _NoDialogs:
    """No REAL dialog may open on the desktop while a test runs (a modal window waits for a person): each one is
    recorded and answered No / cancelled - the test then fails on `asked`."""
    _DIALOGS = ((messagebox, ("askyesno", "askokcancel", "askyesnocancel", "askquestion", "askretrycancel",
                              "showinfo", "showwarning", "showerror")),
                (simpledialog, ("askstring", "askinteger", "askfloat")),
                (filedialog, ("askopenfilename", "askopenfilenames", "asksaveasfilename", "askdirectory")))

    def __enter__(self):
        self.asked, self.saved = [], []
        for module, names in self._DIALOGS:
            for name in names:
                self.saved.append((module, name, getattr(module, name)))
                setattr(module, name, lambda *args, _name=name, **_kwargs: self.asked.append((_name, *args[:2])))
        return self

    def __exit__(self, *_exc):
        for module, name, real in self.saved:
            setattr(module, name, real)


def test_project_copy_helpers():
    """Tk-free: a shipped system config file is recognised, its project copy lands in the resolver's
    tier 1 (and then WINS the resolution), a copy is never overwritten, no project = no target."""
    ok(files_view.is_shipped_system_config(_SHIPPED), "the shipped templates.yaml")
    ok(not files_view.is_shipped_system_config(os.path.join(config.builtin_config_project_dir(), "app_config.yaml")),
       "an app file is not system config")
    eq(files_view.placeholder_map({})["system_config"], SYSTEM.config_root, "the ${system_config} root")
    config.use_project(None)
    eq(files_view.project_copy_target(_SHIPPED), (None, "open a project to create its own copy"), "no project")
    with tempfile.TemporaryDirectory() as root:
        _project(root, templates=None)
        config.use_project(root)
        try:
            target, reason = files_view.project_copy_target(_SHIPPED)
            eq(target, os.path.join(root, "config_project", "systems", SYSTEM.id, "chain_reactions", "templates.yaml"),
               "tier 1 of the resolver")
            eq(files_view.create_project_copy(_SHIPPED), target, "copied")
            with open(target, "rb") as a, open(_SHIPPED, "rb") as b:
                eq(a.read(), b.read(), "byte for byte")
            from pipeline5.config.resolver import find
            eq(os.path.normcase(find("chain_reactions/templates.yaml")), os.path.normcase(target),
               "the copy now wins the resolution")
            try:
                files_view.create_project_copy(_SHIPPED)
                ok(False, "a second copy must not overwrite the first")
            except FileExistsError:
                pass
        finally:
            config.use_project(None)
    with tempfile.TemporaryDirectory() as root:              # C-025 refute round 8 (#3): the project's own copy
        _project(root, templates=None)                        # kept in its SHARED tier (resolver tier 2) runs -
        shared = os.path.join(root, "config_project", "shared", "chain_reactions", "templates.yaml")
        os.makedirs(os.path.dirname(shared))                  # 'Create project copy' put the shipped file at tier
        with open(shared, "w", encoding="utf-8") as handle:   # 1, over it: the project's templates silently gone
            handle.write("mine: x\n")
        config.use_project(root)
        try:
            from pipeline5.config.resolver import find
            eq(os.path.normcase(find("chain_reactions/templates.yaml")), os.path.normcase(shared), "(the shared copy runs)")
            eq(files_view.project_copy_target(_SHIPPED), (shared, None), "the project's copy is the one that runs")
            try:
                files_view.create_project_copy(_SHIPPED)
                ok(False, "a copy must not be made over the project's own")
            except FileExistsError:
                pass
            tier1 = os.path.join(root, "config_project", "systems", SYSTEM.id, "chain_reactions", "templates.yaml")
            ok(not os.path.exists(tier1), "nothing made at tier 1 - the project's own copy still runs")
        finally:
            config.use_project(None)


def test_a_save_bridges_a_readers_brief_hold():
    """C-025 refute round 8 (#1), the Save's half: Windows replaces no file a reader holds (Python's own open shares
    no delete) - a Save pressed while a check read the file failed at once, its temp file left beside it. The
    replace is retried for a moment now: a brief hold is bridged; a lasting one raises with the file as it was -
    and no temp file is left either way. Tk-free."""
    import threading
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "templates.yaml")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("old\n")
        holder = open(path, encoding="utf-8")                  # a reader - held 150 ms
        timer = threading.Timer(0.15, holder.close)
        timer.start()
        try:
            files_view.write_text_file(path, "new\n", False, False)
        finally:
            timer.join()
            holder.close()
        with open(path, encoding="utf-8") as handle:
            eq(handle.read(), "new\n", "a brief hold: saved once it lets go")
        eq(sorted(os.listdir(folder)), ["templates.yaml"], "…no temp file left")
        if os.name != "nt":
            return                                           # (elsewhere a reader never blocks a replace)
        holder = open(path, encoding="utf-8")                  # a hold that outlasts the retries
        try:
            files_view.write_text_file(path, "newer\n", False, False)
            ok(False, "a lasting hold must refuse the Save")
        except PermissionError:
            pass
        finally:
            holder.close()
        with open(path, encoding="utf-8") as handle:
            eq(handle.read(), "new\n", "a lasting hold: the file as it was")
        eq(sorted(os.listdir(folder)), ["templates.yaml"], "…and no temp file left")


def test_template_mode_in_the_files_panel():
    """The real panel: the template mode's layers, a rule + its preview, a lint squiggle and its
    problem row, a completion popup accepted into the text."""
    root = _tk()
    if root is None:
        return
    template_doc.Session = _session
    try:
        with tempfile.TemporaryDirectory() as project:
            path = _project(project)
            config.use_project(project)
            panel = _panel(root, project)
            panel._load(path)
            root.update()
            mode, text = panel._template, panel._textw
            ok(mode is not None, "a templates.yaml opens in the template mode")
            eq(sorted(set(_tagged(text, "tp_directive"))), ["@end", "@for", "in", "where"], "the directives")
            ok("REGION" in _tagged(text, "hl_key"), "the SCL layer underneath")
            ok(_pump(root, lambda: "Choose a rule" in mode.preview.get("1.0", "end")), "the preview invites a rule")
            eq(mode.problems.get_children(), (), "no rule chosen: the document alone is clean")
            mode.rule_box.current(1)
            mode.on_rule()
            ok("building the Database" in mode.preview.get("1.0", "end-1c"), "a worker builds the hook's Database")
            ok(_pump(root, lambda: mode.preview.get("1.0", "end-1c").startswith("APPEND")), "…then the preview")
            eq(str(mode.row_box.cget("to")), "1.0", "the rule's source rows (2) at its hook")
            preview = mode.preview.get("1.0", "end-1c")
            ok(preview.startswith("APPEND to ") and preview.endswith("REGION B1\n  PEC(P1);\nEND_REGION"),
               f"one fire for row 0: {preview!r}")
            text.insert("4.0", "  X {$r.tagg}\n")            # a loop-column typo inside the @for
            mode.refresh()
            ok(_pump(root, lambda: _problem_rows(mode, "tagg")), f"the problem row: {_problem_rows(mode, '')}")
            eq(_tagged(text, "tp_error"), ["$r.tagg"], "…and its squiggle on exactly the typo")
            mode.problems.selection_set(mode.problems.get_children()[0])
            root.update()                                    # the real <<TreeviewSelect>> -> the jump
            eq(text.get("sel.first", "sel.last"), "$r.tagg", "clicking the problem selects the culprit")
            mode.problems.selection_remove(*mode.problems.selection())
            root.update()

            class Key:
                char, keysym = "a", "a"
            text.insert("2.0", "  {$ta\n")
            text.mark_set("insert", "2.6")
            root.update()
            mode._on_key(Key())
            ok(mode.popup.is_open, "the completion popup opened")
            eq(mode.popup.listbox.get(0, "end"), ("$tag",), "the rule's column")
            mode.popup.accept()
            eq(text.get("2.0", "2.end"), "  {$tag", "accepted into the text")
    finally:
        template_doc.Session = _REAL_SESSION
        config.use_project(None)
        _done(root)


def test_every_edit_reaches_the_template_mode():
    """C-025 refute round 3 (F1, HIGH): Tk raised <<Modified>> as the text's modified flag FLIPPED, and the
    Files tab never re-armed it - after the FIRST edit the template mode never re-checked: its problems,
    squiggles and preview showed the old text while a fire rejects the new. Two real edits through the
    panel now - no hand-called refresh or schedule - each is re-checked; the unsaved-changes guard and
    Save still hold."""
    root = _tk()
    if root is None:
        return
    template_doc.Session = _session
    try:
        with tempfile.TemporaryDirectory() as project:
            path = _project(project)
            config.use_project(project)
            panel = _panel(root, project)
            panel._load(path)
            mode, text = panel._template, panel._textw
            mode.rule_box.current(1)
            mode.on_rule()
            ok(_pump(root, lambda: mode.preview.get("1.0", "end-1c").startswith("APPEND")), "the rule's preview")
            ok(not panel._unsaved_changes(), "freshly loaded: clean")
            text.insert("6.0", "  ")                          # edit 1 - harmless
            _pump(root, lambda: False, 0.6)
            ok(panel._unsaved_changes(), "an edit is an unsaved change")
            text.insert("4.0", "  X {$r.tagg}\n")             # edit 2 - a loop-column typo
            ok(_pump(root, lambda: _problem_rows(mode, "tagg")), "the SECOND edit is re-checked")
            eq(_tagged(text, "tp_error"), ["$r.tagg"], "…its squiggle")
            ok("tagg" in mode.preview.get("1.0", "end-1c"), "…and the preview says the fire's finding")
            text.delete("4.0", "5.0")                           # edit 3 - the typo gone again
            ok(_pump(root, lambda: not _problem_rows(mode, "tagg")), "the THIRD edit is re-checked too")
            save = [w for w in _widgets(panel.editor, ttk.Button) if w.cget("text").startswith("Save")]
            save[0].invoke()
            root.update()
            ok(not panel._unsaved_changes(), "saved: clean")
            with open(path, encoding="utf-8") as handle:
                eq(handle.read(), text.get("1.0", "end-1c"), "…the file is the text")
    finally:
        template_doc.Session = _REAL_SESSION
        config.use_project(None)
        _done(root)


def test_the_session_works_off_the_tk_thread():
    """C-025 refute round 2 (#8): the in-hook cascade - the whole Session - ran on the Tk thread (0.5 s
    a keystroke at 20k rows), and a Reload during an in-flight build kept the stale build. Now the
    Session's work runs on the view's ONE worker: the Tk thread stays live while a Database builds, a
    result computed for an older request is dropped, and a Reload waits for the build it would race."""
    import threading
    import time
    root = _tk()
    if root is None:
        return
    gate, builds, calls, active = threading.Event(), [], [], [0]

    def loader(system):
        active[0] += 1
        builds.append(threading.current_thread().name)
        try:
            gate.wait(10)
            return _signals()
        finally:
            active[0] -= 1

    def instrumented(path=None):
        session = _REAL_SESSION(path, hooks={"before_300": None, "after_300": loader})
        for name in ("reload", "base", "view", "check", "row_count", "preview_text", "context"):
            def wrapper(*args, _real=getattr(session, name), _name=name, **kwargs):
                calls.append((_name, threading.current_thread() is threading.main_thread(), active[0]))
                return _real(*args, **kwargs)
            setattr(session, name, wrapper)
        return session

    template_doc.Session = instrumented
    try:
        with tempfile.TemporaryDirectory() as project:
            path = _project(project)
            config.use_project(project)
            panel = _panel(root, project)
            panel._load(path)
            mode, text = panel._template, panel._textw
            applied, apply = [], mode._apply
            mode._apply = lambda result: (applied.append(result[1]), apply(result))
            mode.rule_box.current(1)
            began = time.time()
            mode.on_rule()
            root.update()
            ok(time.time() - began < 1.0, "choosing a rule returns at once - its Database builds on the worker")
            ok("building the Database" in mode.preview.get("1.0", "end-1c"), "…the preview says so")
            ok(_pump(root, lambda: builds, 5), "the build is running")
            stale = mode._request
            text.insert("4.0", "  X {$r.tagg}\n")          # typed WHILE the build runs
            mode.refresh()
            root.update()
            gate.set()
            ok(_pump(root, lambda: _problem_rows(mode, "tagg")), "the newest text's problems")
            ok(stale not in applied, f"the result computed for the older text is dropped ({stale} in {applied})")
            eq(applied, [mode._request], "only the result for the text AS IT IS was applied (one computed for a "
                                         "text edited since it was sent is dropped too)")
            eq(builds, ["template-builder"], "one build, on the worker")
            before = len([name for name, _t, _b in calls if name == "reload"])
            panel.refresh()                                  # after a run / a project or system switch
            ok(_pump(root, lambda: len(builds) == 2, 5) and len([n for n, _t, _b in calls if n == "reload"]) > before,
               "the Files tab's refresh reloads the builder - it re-reads the config and rebuilds, on its worker")
            gate.set()
            ok(_pump(root, lambda: applied[-1:] == [mode._request]), "…and its result comes back")
            del builds[1:]
            gate.clear()
            mode.reload()
            ok(_pump(root, lambda: len(builds) == 2, 5), "a Reload rebuilds the Database")

            class Key:
                char, keysym = "a", "a"
            text.insert("2.0", "  {$ta\n")
            text.mark_set("insert", "2.6")
            root.update()
            mode._on_key(Key())
            ok(not mode.popup.is_open, "while the rules reload, no stale rule columns are offered")
            mode.refresh()                                   # a check queued behind that build…
            mode.reload()                                    # …then a second Reload, both WHILE it runs
            _pump(root, lambda: False, 0.3)
            gate.set()
            ok(_pump(root, lambda: len(builds) == 3 and applied and applied[-1] == mode._request),
               f"…it waits for the build, then rebuilds once more ({builds})")
            reloads = [(on_tk, busy) for name, on_tk, busy in calls if name == "reload"]
            eq(reloads, [(False, 0)] * 3, "each reload (the refresh's + two ↻) ran on the worker, never during a build")
            last = max(i for i, call in enumerate(calls) if call[0] == "reload")
            eq([name for name, _on_tk, _busy in calls[last + 1:] if name == "check"], ["check"],
               "the check queued before that Reload was skipped - one check, against the reloaded rules")
            eq([name for name, on_tk, _busy in calls if on_tk], [], "no Session work on the Tk thread")
            mode._on_key(Key())
            eq(mode.popup.listbox.get(0, "end") if mode.popup.is_open else (), ("$tag",),
               "the reloaded rule's columns complete again")
    finally:
        template_doc.Session = _REAL_SESSION
        config.use_project(None)
        _done(root)


def test_only_the_newest_result_for_the_text_as_it_is_applies():
    """The worker's result discipline, with the timing under the test's control (the worker is held
    inside each `check` until the test lets it finish): a result for an OLDER request, arriving on its
    own, is dropped; so is the newest request's result when the text was edited after it was sent (its
    positions would squiggle the wrong characters); the next result applies."""
    import threading
    from pipeline5.workbench import template_mode
    root = _tk()
    if root is None:
        return
    permits, held, inside = threading.Semaphore(0), [False], threading.Event()

    def instrumented(path=None):
        session = _session(path)

        def check(*args, _real=session.check, **kwargs):
            if held[0]:
                inside.set()                                 # the test knows the worker is here
                permits.acquire(timeout=10)
            return _real(*args, **kwargs)
        session.check = check
        return session

    template_doc.Session = instrumented
    debounce = template_mode._DEBOUNCE_MS
    try:
        with tempfile.TemporaryDirectory() as project:
            path = _project(project)
            config.use_project(project)
            panel = _panel(root, project)
            panel._load(path)
            mode = panel._template
            mode.rule_box.current(1)
            mode.on_rule()
            ok(_pump(root, lambda: mode.preview.get("1.0", "end-1c").startswith("APPEND")), "the rule's first result")
            applied, apply = [], mode._apply
            mode._apply = lambda result: (applied.append(result[1]), apply(result))
            held[0] = True
            inside.clear()
            mode.refresh()                                   # the worker is held inside its check…
            ok(inside.wait(5), "the worker is inside the older request's check")
            mode.refresh()                                   # …a newer request queued behind it
            permits.release()                                # only the OLDER one completes
            _pump(root, lambda: False, 0.5)
            eq(applied, [], "a result for an older request, arriving on its own, is dropped")
            permits.release()
            ok(_pump(root, lambda: applied == [mode._request]), f"…the newest one applies ({applied})")
            template_mode._DEBOUNCE_MS = 5000                # the edit's own refresh must not come first
            inside.clear()
            mode.refresh()
            sent = mode._request
            ok(inside.wait(5), "the worker is inside that request's check")
            mode.schedule()                                  # the text is edited after that request was sent
            permits.release()
            _pump(root, lambda: False, 0.5)
            ok(sent not in applied, f"the newest request's result, for a text edited since, is dropped ({applied})")
            mode.refresh()
            permits.release()
            ok(_pump(root, lambda: applied[-1:] == [mode._request]), f"…and the fresh one applies ({applied})")
            import time                                      # C-025 refute round 4 (F4): the poll can run BEFORE
            inside.clear()                                   # an edit's <<Modified>> handler (which sets _editing)
            mode.refresh()
            ok(inside.wait(5), "the worker is inside the check")
            seen = list(applied)
            panel._textw.insert("1.0", "# typed\n")        # a keystroke - its <<Modified>> not yet handled
            permits.release()
            deadline = time.time() + 5
            while mode._results.empty() and time.time() < deadline:
                time.sleep(0.02)                             # (no Tk events processed meanwhile)
            ok(not mode._results.empty(), "the result for the text BEFORE the keystroke is in")
            mode._drain()                                    # the 100 ms poll first
            eq(applied, seen, "…and never applied: it was computed for another text (its positions would be wrong)")
    finally:
        template_mode._DEBOUNCE_MS = debounce
        held[0] = False
        for _ in range(4):                                   # a failed assertion must not strand the worker
            permits.release()
        template_doc.Session = _REAL_SESSION
        config.use_project(None)
        _done(root)


def test_the_shipped_file_is_read_only_until_copied():
    """The shipped templates.yaml opens read-only; 'Create project copy' writes the project's tier-1
    copy and opens it - editable, in the template mode."""
    root = _tk()
    if root is None:
        return
    try:
        with tempfile.TemporaryDirectory() as project:
            _project(project, templates=None)
            config.use_project(project)
            panel = _panel(root, project)
            panel._load(_SHIPPED)
            root.update()
            eq(str(panel._textw.cget("state")), "disabled", "read-only")
            ok(panel._template is not None, "…still in the template mode (lint + preview, no edits)")
            buttons = _buttons(panel.editor)
            ok("Create project copy" in buttons, f"the copy button ({buttons})")
            panel._project_copy(_SHIPPED)
            root.update()
            target = files_view.project_copy_target(_SHIPPED)[0]
            eq(os.path.normcase(panel._cur), os.path.normcase(target), "the copy is shown")
            eq(str(panel._textw.cget("state")), "normal", "…editable")
    finally:
        config.use_project(None)
        _done(root)


def _widgets(widget, kind) -> list:
    """Every widget of class `kind` under `widget` (recursive)."""
    found = [widget] if isinstance(widget, kind) else []
    for child in widget.winfo_children():
        found += _widgets(child, kind)
    return found


def test_every_viewer_keeps_the_shipped_config_read_only():
    """Not only the text editor: the CSV grid (it edits cells in place) and the Object explorer (it
    saves) keep a shipped system config file read-only - each with the copy button - while a
    project file of the same kinds stays editable."""
    root = _tk()
    if root is None:
        return
    from pipeline5.workbench import datagrid, object_editor
    try:
        with tempfile.TemporaryDirectory() as project:
            _project(project, templates=None)
            config.use_project(project)
            panel = _panel(root, project)
            shipped_csv = os.path.join(SYSTEM.config_root, "classification", "gate_rules.csv")   # data rows
            with open(shipped_csv, "rb") as handle:
                before = handle.read()
            panel._load(shipped_csv)
            root.update()
            eq([grid._editable for grid in _widgets(panel.editor, datagrid.DataGrid)], [False],
               "the shipped CSV grid is read-only")
            ok("Create project copy" in _buttons(panel.editor) and "Save" not in _buttons(panel.editor),
               f"…with the copy button, no Save ({_buttons(panel.editor)})")
            with open(shipped_csv, "rb") as handle:
                eq(handle.read(), before, "the shipped file is untouched")
            own_csv = os.path.join(project, "config_project", "systems", SYSTEM.id, "chain_reactions", "reactions.csv")
            panel._load(own_csv)
            root.update()
            eq([grid._editable for grid in _widgets(panel.editor, datagrid.DataGrid)], [True], "a project CSV edits")
            panel._obj_mode = True                            # the user prefers the Object explorer
            panel._load(_SHIPPED)
            root.update()
            eq(_widgets(panel.editor, object_editor.ObjectEditor), [], "no Object explorer on a shipped file")
            eq(str(panel._textw.cget("state")), "disabled", "…its read-only Text view instead")
            own_yaml = os.path.join(project, "config_project", "shared", "project_params.yaml")
            panel._load(own_yaml)
            root.update()
            eq(len(_widgets(panel.editor, object_editor.ObjectEditor)), 1, "a project yaml keeps the preference")
    finally:
        config.use_project(None)
        _done(root)


def test_a_check_queued_behind_a_reload_is_dropped():
    """C-025 refute round 6 (#1) through the real FilesPanel: a Reload queued while the worker builds, then a check
    queued behind it - a refresh reads session.rules BEFORE the reload publishes. The worker ran the reload, then
    that check with the pre-reload Rule: the view cache poisoned (every add_rows rule cascaded, the rule's own
    included) and the preview applied afterwards was not the fire's. A stale rule's check is dropped now - the
    reload's labels bring a fresh one."""
    root = _tk()
    if root is None:
        return
    import threading
    from pipeline5.phases.chain_reactions import engine
    rules = ("name,fire_when,source_table,condition,action,target,template,comment\n"
             "cnt,after_300,,,file,gen/c.txt,cnt_txt,\n"
             "sp,after_300,signals,,add_rows,dst,rows,\n")
    templates = 'cnt_txt: |-\n  dst has {count(dst)} rows\nrows:\n  - label: "L-{$tag}"\n'

    def database():
        base = _signals()
        base.add_table(Table("dst", columns=["uid", "label", "spawned_by", "source_uid"], key_columns=["label"]))
        return base

    gate, builds = threading.Event(), []
    gate.set()

    def loader(system):
        builds.append(1)
        gate.wait(10)
        return database()

    template_doc.Session = lambda path=None: _REAL_SESSION(path, hooks={"before_300": None, "after_300": loader})
    try:
        with tempfile.TemporaryDirectory() as proj, tempfile.TemporaryDirectory() as out, \
                tempfile.TemporaryDirectory() as dbdir:
            path = _project(proj, templates)
            with open(os.path.join(os.path.dirname(path), "reactions.csv"), "w", encoding="utf-8") as handle:
                handle.write(rules)
            config.use_project(proj)
            original_db = config.database_dir
            config.database_dir = lambda: dbdir
            try:
                header, *lines = rules.splitlines()
                compiled, _findings = engine.compile_rules([dict(zip(header.split(","), line.split(","))) for line in lines])
                engine.fire("after_300", database(), rules=compiled, templates=template_doc.parse(templates).templates,
                            params={}, files_root=out, hooks=("before_300", "after_300"))
                with open(os.path.join(out, "gen", "c.txt"), encoding="utf-8") as handle:
                    fired = handle.read().splitlines()
                eq(fired, ["dst has 0.0 rows"], "(the fire: cnt runs before sp spawns)")
                panel = _panel(root, proj)
                panel._load(path)
                mode = panel._template
                mode.rule_box.current(1)
                mode.on_rule()

                def shown():
                    text = mode.preview.get("1.0", "end-1c")
                    return text.splitlines()[1:2] if text.startswith("APPEND") and not mode._editing else None
                ok(_pump(root, lambda: shown() is not None), "the preview comes")
                eq(shown(), fired, "first: the fire's line")
                gate.clear()
                mode.reload()                                   # a Reload - its labels' fresh check builds...
                ok(_pump(root, lambda: len(builds) >= 2, 5), "(the worker is inside that build)")
                mode.reload()                                   # ...a second Reload, and a check queued behind it
                mode.refresh()                                  # with the rule read BEFORE that reload publishes
                _pump(root, lambda: False, 0.3)
                gate.set()
                _pump(root, lambda: False, 1.5)
                ok(_pump(root, lambda: shown() is not None, 5), "the preview comes back")
                eq(shown(), fired, "after the reloads: still the fire's line - the stale check dropped")
            finally:
                config.database_dir = original_db
    finally:
        template_doc.Session = _REAL_SESSION
        config.use_project(None)
        _done(root)


def test_a_save_rechecks_the_file_a_fire_reads():
    """C-025 refute round 7 (#1) through the real FilesPanel: a templates.yaml saved as cp1252 opens (its é shown as
    U+FFFD) and the builder said "no problems" while every fire reads the SAVED file and is blocked. The problems list
    and the preview say the fire's rx_templates_unreadable now; an unsaved edit lifts nothing (the fire reads the
    file); Save re-checks - the file UTF-8 now, the problem gone, the preview back."""
    root = _tk()
    if root is None:
        return
    template_doc.Session = _session
    try:
        with _NoDialogs() as dialogs, tempfile.TemporaryDirectory() as project:
            path = _project(project)
            with open(path, "w", encoding="cp1252", newline="\n") as handle:
                handle.write("# Température\n" + _TEMPLATES)
            config.use_project(project)
            panel = _panel(root, project)
            panel._load(path)
            mode, text = panel._template, panel._textw
            applied, apply = [], mode._apply
            mode._apply = lambda result: (applied.append(result[1]), apply(result))
            ok(_pump(root, lambda: _problem_rows(mode, "rx_templates_unreadable")), "the fire's finding is listed")
            eq(text.get("1.0", "1.end"), "# Temp�rature", "(the pane shows the undecodable byte as U+FFFD)")
            mode.rule_box.current(1)
            mode.on_rule()
            ok(_pump(root, lambda: mode.preview.get("1.0", "end-1c").startswith("rx_templates_unreadable: ")),
               f"…the preview says it: {mode.preview.get('1.0', 'end-1c')!r}")
            text.delete("1.6", "1.7")
            text.insert("1.6", "é")                              # the é retyped: an unsaved edit
            ok(_pump(root, lambda: not mode._editing and applied[-1:] == [mode._request]), "(the edit is re-checked)")
            ok(_problem_rows(mode, "rx_templates_unreadable"), "an unsaved edit lifts nothing - a fire reads the file")
            save = [w for w in _widgets(panel.editor, ttk.Button) if w.cget("text").startswith("Save")]
            save[0].invoke()
            ok(_pump(root, lambda: not _problem_rows(mode, "rx_templates_unreadable"), 5),
               f"Save re-checks: the problem gone ({_problem_rows(mode, '')})")
            ok(_pump(root, lambda: mode.preview.get("1.0", "end-1c").startswith("APPEND")), "…the preview back")
            with open(path, "rb") as handle:
                eq(handle.read().split(b"\n")[0], "# Température".encode("utf-8"), "(the file: UTF-8 now)")
            eq(dialogs.asked, [], "no dialog asked")
    finally:
        template_doc.Session = _REAL_SESSION
        config.use_project(None)
        _done(root)


def test_a_reload_keeps_the_chosen_rule_of_two_alike():
    """C-025 refute round 7 (#3): after a reload - the ↻ button, the Files tab's refresh after every run and on a
    project / system switch - the view re-found the chosen rule by its LABEL: the first of two alike (round 6: two
    identical reactions.csv lines are two rules), its label unchanged while the checks and the preview judged the
    other rule. The same occurrence of the label is chosen now."""
    from pipeline5.phases.chain_reactions import engine
    from pipeline5.workbench import template_mode
    labels = ["(none)", "a", "b", "a"]
    eq([template_mode._reselect(labels, template_mode._chosen(labels, i)) for i in range(4)], [0, 1, 2, 3],
       "each rule its own place - the second 'a' too")
    eq(template_mode._reselect(["(none)", "x", "a", "b", "a"], template_mode._chosen(labels, 3)), 4,
       "a rule added before them: the same occurrence")
    eq(template_mode._reselect(["(none)", "a"], template_mode._chosen(labels, 3)), 1, "one of the two gone: the one left")
    eq(template_mode._reselect(["(none)", "b"], template_mode._chosen(labels, 1)), 0, "its label gone: no rule")
    root = _tk()
    if root is None:
        return
    rules = ("name,fire_when,source_table,condition,action,target,template,comment\n"
             "cnt,after_300,,,file,gen/c.txt,cnt_txt,\n"
             "sp,after_300,signals,,add_rows,dst,rows,\n"
             "cnt,after_300,,,file,gen/c.txt,cnt_txt,\n")
    templates = 'cnt_txt: |-\n  dst has {count(dst)} rows\nrows:\n  - label: "L-{$tag}"\n'

    def database():
        base = _signals()
        base.add_table(Table("dst", columns=["uid", "label", "spawned_by", "source_uid"], key_columns=["label"]))
        return base

    template_doc.Session = lambda path=None: _REAL_SESSION(path, hooks={"before_300": None,
                                                                         "after_300": lambda system: database()})
    try:
        with _NoDialogs() as dialogs, tempfile.TemporaryDirectory() as proj, tempfile.TemporaryDirectory() as out, \
                tempfile.TemporaryDirectory() as dbdir:
            path = _project(proj, templates)
            with open(os.path.join(os.path.dirname(path), "reactions.csv"), "w", encoding="utf-8") as handle:
                handle.write(rules)
            config.use_project(proj)
            original_db = config.database_dir
            config.database_dir = lambda: dbdir
            try:
                header, *lines = rules.splitlines()
                compiled, _findings = engine.compile_rules([dict(zip(header.split(","), line.split(","))) for line in lines])
                engine.fire("after_300", database(), rules=compiled, templates=template_doc.parse(templates).templates,
                            params={}, files_root=out, hooks=("before_300", "after_300"))
                with open(os.path.join(out, "gen", "c.txt"), encoding="utf-8") as handle:
                    fired = handle.read().splitlines()
                eq(fired, ["dst has 0.0 rows", "dst has 2.0 rows"], "(the fire: the first cnt before sp, the second after)")
                panel = _panel(root, proj)
                panel._load(path)
                mode = panel._template
                applied, apply = [], mode._apply
                mode._apply = lambda result: (applied.append(result[1]), apply(result))

                def shown():
                    text = mode.preview.get("1.0", "end-1c")
                    return text.splitlines()[1:2] if text.startswith("APPEND") else None
                mode.rule_box.current(3)                                # the user picks the SECOND cnt
                mode.on_rule()
                ok(_pump(root, lambda: applied[-1:] == [mode._request] and shown() == fired[1:]),
                   f"the second cnt: its own fire's line ({shown()})")
                for reload in (panel.refresh, mode.reload):             # after a run / a switch, and the ↻ button
                    before = mode._request
                    reload()
                    ok(_pump(root, lambda: mode._request >= before + 2 and applied[-1:] == [mode._request]),
                       f"{reload.__name__}: the reloaded rules' check comes back")
                    eq((mode.rule_box.current(), shown()), (3, fired[1:]),
                       f"{reload.__name__}: still the second cnt - its own fire's line")
                with open(os.path.join(os.path.dirname(path), "reactions.csv"), "w", encoding="utf-8") as handle:
                    handle.write("\n".join([header, "x,after_300,,,file,gen/x.txt,cnt_txt,", *lines]) + "\n")
                for number in (1, 2):                                   # a rule added before them: the same one at
                    before = mode._request                              # its new place - and so on the next reload
                    mode.reload()
                    ok(_pump(root, lambda: mode._request >= before + 2 and applied[-1:] == [mode._request]),
                       f"reload {number} over the changed rules: its check comes back")
                    eq((mode.rule_box.current(), shown()), (4, fired[1:]),
                       f"reload {number} over the changed rules: the second cnt, at its new place")
                eq(dialogs.asked, [], "no dialog asked")
            finally:
                config.database_dir = original_db
    finally:
        template_doc.Session = _REAL_SESSION
        config.use_project(None)
        _done(root)


def test_a_save_never_fails_on_the_builders_read():
    """C-025 refute round 8 (#1) through the real FilesPanel: every check reads the templates.yaml a fire reads, and
    the loader parsed it INSIDE its `open` - a Save pressed while the worker parsed it failed ("Access is denied":
    Windows replaces no file a reader holds), 2 Saves in 4 in the refuter's run. The worker held inside that parse
    now, a Save goes through: saved, the file the text, no temp file left; the check then completes."""
    import threading
    from ruamel.yaml import YAML
    root = _tk()
    if root is None:
        return
    template_doc.Session = _session
    real_load, inside, release = YAML.load, threading.Event(), threading.Event()
    try:
        with _NoDialogs() as dialogs, tempfile.TemporaryDirectory() as project:
            path = _project(project)
            config.use_project(project)
            panel = _panel(root, project)
            statuses = []
            panel.on_status = statuses.append
            panel._load(path)
            mode, text = panel._template, panel._textw
            applied, apply = [], mode._apply
            mode._apply = lambda result: (applied.append(result[1]), apply(result))
            ok(_pump(root, lambda: applied[-1:] == [mode._request]), "(the first check)")

            def held(self, stream):                          # the worker, parsing the saved file, waits here
                if threading.current_thread().name == "template-builder" and \
                        os.path.normcase(str(getattr(stream, "name", ""))) == os.path.normcase(path):
                    inside.set()
                    release.wait(10)
                return real_load(self, stream)
            YAML.load = held
            text.insert("1.0", "# saved while the builder reads\n")
            ok(_pump(root, inside.is_set, 5), "the worker is inside the saved file's parse")
            save = [w for w in _widgets(panel.editor, ttk.Button) if w.cget("text").startswith("Save")]
            save[0].invoke()
            eq(statuses[-1:], ["saved templates.yaml"], "the Save went through")
            with open(path, encoding="utf-8") as handle:
                eq(handle.read(), text.get("1.0", "end-1c"), "…the file is the text")
            eq(sorted(os.listdir(os.path.dirname(path))), ["reactions.csv", "templates.yaml"], "…no temp file left")
            ok(not panel._unsaved_changes(), "…clean")
            release.set()
            YAML.load = real_load
            ok(_pump(root, lambda: not mode._editing and applied[-1:] == [mode._request]), "the check completes")
            eq(dialogs.asked, [], "no dialog asked")
    finally:
        release.set()
        YAML.load = real_load
        template_doc.Session = _REAL_SESSION
        config.use_project(None)
        _done(root)


def test_open_project_copy_goes_to_the_one_that_runs():
    """C-025 refute round 8 (#3) through the real FilesPanel: with the project's own templates.yaml in its SHARED
    tier, the shipped file offered 'Create project copy' - which put the shipped file at tier 1, over the project's
    own. It offers 'Open project copy' now, and that opens the copy that runs."""
    root = _tk()
    if root is None:
        return
    try:
        with _NoDialogs() as dialogs, tempfile.TemporaryDirectory() as project:
            _project(project, templates=None)
            shared = os.path.join(project, "config_project", "shared", "chain_reactions", "templates.yaml")
            os.makedirs(os.path.dirname(shared))
            with open(shared, "w", encoding="utf-8") as handle:
                handle.write("mine: x\n")
            config.use_project(project)
            panel = _panel(root, project)
            panel._load(_SHIPPED)
            root.update()
            buttons = _buttons(panel.editor)
            ok("Open project copy" in buttons and "Create project copy" not in buttons, f"the button ({buttons})")
            panel._project_copy(_SHIPPED)
            root.update()
            eq(os.path.normcase(panel._cur), os.path.normcase(shared), "the project's own copy is shown - the one that runs")
            tier1 = os.path.join(project, "config_project", "systems", SYSTEM.id, "chain_reactions", "templates.yaml")
            ok(not os.path.exists(tier1), "nothing made at tier 1")
            eq(dialogs.asked, [], "no dialog asked")
    finally:
        config.use_project(None)
        _done(root)


if __name__ == "__main__":
    import sys
    sys.exit(run("gui_template_mode", [
        ("project_copy_helpers", test_project_copy_helpers),
        ("a_save_bridges_a_readers_brief_hold", test_a_save_bridges_a_readers_brief_hold),
        ("template_mode_in_the_files_panel", test_template_mode_in_the_files_panel),
        ("every_edit_reaches_the_template_mode", test_every_edit_reaches_the_template_mode),
        ("the_session_works_off_the_tk_thread", test_the_session_works_off_the_tk_thread),
        ("only_the_newest_result_for_the_text_as_it_is_applies",
         test_only_the_newest_result_for_the_text_as_it_is_applies),
        ("the_shipped_file_is_read_only_until_copied", test_the_shipped_file_is_read_only_until_copied),
        ("every_viewer_keeps_the_shipped_config_read_only", test_every_viewer_keeps_the_shipped_config_read_only),
        ("a_check_queued_behind_a_reload_is_dropped", test_a_check_queued_behind_a_reload_is_dropped),
        ("a_save_rechecks_the_file_a_fire_reads", test_a_save_rechecks_the_file_a_fire_reads),
        ("a_reload_keeps_the_chosen_rule_of_two_alike", test_a_reload_keeps_the_chosen_rule_of_two_alike),
        ("a_save_never_fails_on_the_builders_read", test_a_save_never_fails_on_the_builders_read),
        ("open_project_copy_goes_to_the_one_that_runs", test_open_project_copy_goes_to_the_one_that_runs),
    ]))
