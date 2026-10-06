"""C-026 - the Files tab never drops an unsaved edit without asking - driven through the REAL FilesPanel on an
off-screen Tk root (SKIPPED where no display exists), `tkinter.messagebox.askyesno` answering both ways. Each
viewer that edits - the text pane (the template mode's included), the CSV grid, the Object explorer - is made
dirty for real, then every path that would replace or close it runs: another file picked in the tree, the
Text <-> Object explorer toggle, the project-copy jump, the App's close. A light/dark switch re-themes in place;
the text pane is clean again once its text is back to the saved one; Revert is the deliberate discard; a text pane
that goes takes its pending timers with it."""
import os
import re
import tempfile
import tkinter.filedialog as filedialog
import tkinter.messagebox as messagebox
import tkinter.simpledialog as simpledialog
import types
from tkinter import ttk

from openpyxl import Workbook

from _harness import run, eq, ok
from pipeline5 import config
from pipeline5.workbench import datagrid, files_view, object_editor, template_doc, theme
from pipeline5.workbench import syntax_highlight as highlight
from filexy import objectview                                 # (on sys.path once the object_editor shim loaded)
from test_gui_template_mode import _REAL_SESSION, _SHIPPED, _done, _panel, _project, _pump, _session, _tk, _widgets

_CSV = "name,qty\r\nbelt,1\r\npec,2\r\n"
_NOTES = "line one\nline two\n"


def _fixture(root) -> dict:
    """A temp project - the template tests' rules + templates.yaml (tier 1) - plus one file per viewer: a
    yaml (Text / Object explorer), a CSV (the grid), an xlsx with two sheets, a plain text file."""
    templates = _project(root)
    shared = os.path.join(root, "config_project", "shared")
    paths = {"templates": templates, "yaml": os.path.join(shared, "project_params.yaml"),
             "csv": os.path.join(shared, "table.csv"), "xlsx": os.path.join(shared, "book.xlsx"),
             "text": os.path.join(shared, "notes.txt")}
    with open(paths["csv"], "w", encoding="utf-8", newline="") as handle:
        handle.write(_CSV)
    with open(paths["text"], "w", encoding="utf-8", newline="\n") as handle:
        handle.write(_NOTES)
    book = Workbook()
    book.active.title = "first"
    book.active.append(["a", "b"])
    book.active.append(["1", "2"])
    second = book.create_sheet("second")
    second.append(["x", "y", "z"])
    second.append(["7", "8", "9"])
    book.save(paths["xlsx"])
    paths["big"] = os.path.join(shared, "big.csv")             # enough rows to scroll
    with open(paths["big"], "w", encoding="utf-8", newline="") as handle:
        handle.write("name,qty\r\n" + "".join(f"row{i},{i}\r\n" for i in range(200)))
    paths["doc"] = os.path.join(shared, "paths.yaml")          # a path key (the … picker) and a list
    with open(paths["doc"], "w", encoding="utf-8", newline="\n") as handle:
        handle.write("input_path: docs/io.xlsx\nitems:\n  - a\n")
    return paths


class _Answer:
    """`messagebox.askyesno` answering `yes`, recording every question asked (the FilesPanel imports the module
    when it asks, so patching the module attribute reaches it)."""

    def __init__(self, yes: bool):
        self.yes, self.asked = yes, []

    def __call__(self, _title, message, **_kwargs):
        self.asked.append(message)
        return self.yes

    def __enter__(self):
        self._real, messagebox.askyesno = messagebox.askyesno, self
        return self

    def __exit__(self, *_exc):
        messagebox.askyesno = self._real


class _Patched:
    """Temporarily replace `module.name` (a dialog, a writer) - restored on exit, whatever happens."""

    def __init__(self, *replacements):
        self.replacements = replacements                         # (module, name, value) triples

    def __enter__(self):
        self.saved = [(module, name, getattr(module, name)) for module, name, _value in self.replacements]
        for module, name, value in self.replacements:
            setattr(module, name, value)
        return self

    def __exit__(self, *_exc):
        for module, name, real in self.saved:
            setattr(module, name, real)


_DIALOGS = ((messagebox, "askyesno"), (simpledialog, "askstring"), (filedialog, "askopenfilename"),
            (filedialog, "askdirectory"))
_UNEXPECTED: list = []                                       # questions no _Answer / _Patched was set up for
_GUARD: list = []                                            # the running test's dialog guard


def _no_real_dialog(*args, **_kwargs):
    """Stands in for every real dialog while a test runs: a question no `_Answer` / `_Patched` expected is
    recorded - the test fails at its end - and answered No / cancelled, the safe side. A real modal window would
    open on the desktop and wait for a person (it did, once: a guard left unpatched)."""
    _UNEXPECTED.append(" / ".join(str(arg) for arg in args[:2]))
    return False


def _refuse(*_args, **_kwargs):
    """A writer the OS refuses - what a save meets when the file is held open (Excel does that to a CSV)."""
    raise PermissionError(13, "Access is denied")


def _question(path) -> list:
    return [f"Discard unsaved changes to {os.path.basename(path)}?"]


def _disk(path) -> bytes:
    with open(path, "rb") as handle:
        return handle.read()


def _item(panel, path):
    wanted = os.path.normcase(path)
    return next(item for item, known in panel._paths.items() if os.path.normcase(known) == wanted)


def _pick(root, panel, path) -> None:
    """Select `path` in the tree as a click does - the real <<TreeviewSelect>> runs the panel's handler."""
    panel.tree.selection_set(_item(panel, path))
    root.update()


def _type(root, panel, index, text) -> None:
    """A real edit of the text pane - its <<Modified>> handled."""
    panel._textw.insert(index, text)
    root.update()


def _event(root, panel, name) -> None:
    """A text-pane virtual event (<<Undo>> / <<Redo>> - what Ctrl+Z / Ctrl+Y raise) through the Text bindings."""
    panel._textw.event_generate(name)
    root.update()


def _grid(panel):
    return _widgets(panel.editor, datagrid.DataGrid)[0]


def _object(panel):
    found = _widgets(panel.editor, object_editor.ObjectEditor)
    return found[0] if found else None


def _value_item(editor, key):
    return next(item for item, (path, _role, editable) in editor._rows.items() if editable and path[-1] == key)


def _commit_value(panel, key, value):
    """An Object-explorer value committed - what Enter in its value editor runs."""
    editor = _object(panel)
    item = _value_item(editor, key)
    editor._commit_edit(item, editor._rows[item][0], value)
    return editor


def _toggle(root, panel, side: str) -> None:
    """A click on the Text / Object explorer toggle (`invoke`: the variable set, then the command)."""
    next(w for w in _widgets(panel.editor, ttk.Radiobutton) if w.cget("text") == side).invoke()
    root.update()


def _shown_side(panel) -> list:
    return [w.cget("text") for w in _widgets(panel.editor, ttk.Radiobutton) if w.instate(["selected"])]


def _button(widget, prefix):
    return next(w for w in _widgets(widget, ttk.Button) if str(w.cget("text")).startswith(prefix))


def _mark(panel) -> str:
    """The text pane's modified mark (the label in its Save bar)."""
    return "".join(str(w.cget("text")) for w in _widgets(panel.editor, ttk.Label) if "modified" in str(w.cget("text")))


def _timers(root) -> list:
    """The root's pending `after` jobs, sorted, as (function, alive) pairs: tkinter names a job's Tcl command
    <id><function name> and deletes a widget's commands when it is destroyed - a job not alive fires into nothing."""
    jobs = []
    for job in root.tk.splitlist(root.tk.call("after", "info")):
        command = root.tk.splitlist(root.tk.call("after", "info", job))[0]
        jobs.append((re.sub(r"^\d+", "", command), bool(root.tk.call("info", "commands", command))))
    return sorted(jobs)


def _begin():
    """(root, tempdir, paths, panel) - the panel lists the project's config_project; None without a display.
    `paths["disk"]` keeps every fixture file's bytes as written (_project writes in the platform's newlines)."""
    root = _tk()
    if root is None:
        return None
    _GUARD[:] = [_Patched(*[(module, name, _no_real_dialog) for module, name in _DIALOGS])]
    _GUARD[0].__enter__()                                    # no real dialog from here to _end
    template_doc.Session = _session                          # the template mode's Database: synthetic, no staging
    project = tempfile.TemporaryDirectory()
    paths = _fixture(project.name)
    paths["disk"] = {key: _disk(path) for key, path in list(paths.items())}
    config.use_project(project.name)
    return root, project, paths, _panel(root, project.name)


def _end(root, project) -> None:
    template_doc.Session = _REAL_SESSION
    config.use_project(None)
    _GUARD[0].__exit__(None, None, None)
    _done(root)
    project.cleanup()
    unexpected, _UNEXPECTED[:] = list(_UNEXPECTED), []
    eq(unexpected, [], "every question was one the test expected (an unexpected one would have opened a real dialog)")


def test_another_file_asks_for_every_viewer():
    """A tree pick over each editing viewer that holds an unsaved change asks; No keeps the very same viewer, its
    edit and the tree's selection on the shown file; Yes shows the other file - the edit never written. A clean
    viewer is left without a question. (Gap 2: the Object explorer's edits went without one.)"""
    begun = _begin()
    if begun is None:
        return
    root, project, paths, panel = begun
    try:
        def text_case():
            _type(root, panel, "1.0", "# edited\n")
            return panel._textw, lambda: panel._textw.get("1.0", "2.0") == "# edited\n"

        def template_case():
            mode = panel._template
            ok(mode is not None, "templates.yaml opens in the template mode")
            _type(root, panel, "1.0", "# edited\n")
            return panel._textw, lambda: panel._template is mode and panel._textw.get("1.0", "2.0") == "# edited\n"

        def csv_case():
            grid = _grid(panel)
            grid._commit_cell(0, 1, "99")                      # what Enter in the cell editor runs
            return grid, lambda: panel._csv_dirty and _grid(panel) is grid and grid._rows[0][1] == "99"

        def object_case():
            editor = _commit_value(panel, "project_code", "9Z")
            item = _value_item(editor, "project_code")
            return editor, lambda: editor.dirty and editor.tree.set(item, "value") == "9Z"

        for name, path, object_mode, edit in (("text", paths["text"], False, text_case),
                                              ("template", paths["templates"], False, template_case),
                                              ("csv", paths["csv"], False, csv_case),
                                              ("object", paths["yaml"], True, object_case)):
            panel._obj_mode = object_mode
            with _Answer(False) as never:
                _pick(root, panel, path)
            eq(never.asked, [], f"{name}: opening it from a clean viewer asks nothing")
            eq(os.path.normcase(panel._cur), os.path.normcase(path), f"{name}: shown")
            ok(not panel._unsaved_changes(), f"{name}: freshly opened - clean")
            before = _disk(path)
            widget, still_edited = edit()
            ok(panel._unsaved_changes(), f"{name}: the edit is an unsaved change")
            with _Answer(False) as no:
                _pick(root, panel, paths["xlsx"])
            eq(no.asked, _question(path), f"{name}: picking another file asks")
            ok(widget.winfo_exists() and still_edited(), f"{name}: No keeps the same viewer with its edit")
            eq(os.path.normcase(panel._cur), os.path.normcase(path), f"{name}: …still the shown file")
            eq(panel.tree.selection(), (_item(panel, path),), f"{name}: …the tree back on it")
            with _Answer(True) as yes:
                _pick(root, panel, paths["xlsx"])
            eq(yes.asked, _question(path), f"{name}: asked again")
            eq(os.path.normcase(panel._cur), os.path.normcase(paths["xlsx"]), f"{name}: Yes shows the other file")
            ok(not widget.winfo_exists(), f"{name}: …the edited viewer gone")
            eq(_disk(path), before, f"{name}: …its edit never written")

        panel._obj_mode = False                                # a project / system switch re-sections the tree:
        _pick(root, panel, paths["text"])                     # the edited file is no longer listed
        _type(root, panel, "1.0", "# edited\n")
        text = panel._textw
        rx = os.path.dirname(paths["templates"])
        panel.set_sections([{"title": "rules", "roots": [rx], "include": [re.compile(".*")], "exclude": []}])
        root.update()
        with _Answer(False) as no:
            _pick(root, panel, os.path.join(rx, "reactions.csv"))
        eq(no.asked, _question(paths["text"]), "a pick after the switch asks")
        eq(panel.tree.selection(), (), "No: no selection - the tree does not list the shown file")
        ok(panel._textw is text and text.get("1.0", "2.0") == "# edited\n", "…the edited pane kept")
        with _Answer(True) as yes:
            _pick(root, panel, os.path.join(rx, "reactions.csv"))
        eq((yes.asked, os.path.basename(panel._cur)), (_question(paths["text"]), "reactions.csv"),
           "picked again: asked again, and Yes opens it")
    finally:
        _end(root, project)


def test_a_refresh_keeps_every_viewer():
    """A refresh - after every run, and with new sections on a project / system switch (the App calls both) - only
    re-lists the tree: whatever is shown stays the same widget with its unsaved edit (a committed CSV cell, a
    committed Object-explorer value, typed text, the template mode's - its builder re-reads rules + data, never
    the text) or its view (an xlsx's second sheet), and nothing asks. (Refute round 1: a reload of only some
    viewer kinds passed the template-only pin.)"""
    begun = _begin()
    if begun is None:
        return
    root, project, paths, panel = begun
    try:
        sections = panel.sections
        rules_only = [{"title": "rules", "roots": [os.path.dirname(paths["templates"])], "include": [re.compile(".*")],
                       "exclude": []}]

        def refreshes(name, kept):
            with _Answer(False) as never:
                for step in (panel.refresh, lambda: panel.set_sections(rules_only), lambda: panel.set_sections(sections)):
                    step()
                    _pump(root, lambda: False, 0.3)            # (an open builder reloads on its worker)
                    ok(kept(), f"{name}: kept through {getattr(step, '__name__', 'set_sections')}")
            eq(never.asked, [], f"{name}: a refresh asks nothing")

        _pick(root, panel, paths["csv"])
        grid = _grid(panel)
        grid._commit_cell(0, 1, "99")
        refreshes("csv", lambda: _grid(panel) is grid and panel._csv_dirty and grid._rows[0][1] == "99")
        with _Answer(True):
            _pick(root, panel, paths["xlsx"])
        box = _widgets(panel.editor, ttk.Combobox)[0]
        box.set("second")
        box.event_generate("<<ComboboxSelected>>")
        root.update()
        grid = _grid(panel)
        refreshes("xlsx", lambda: _grid(panel) is grid and box.get() == "second" and grid._columns == ["x", "y", "z"])
        panel._obj_mode = True
        _pick(root, panel, paths["yaml"])
        editor = _commit_value(panel, "project_code", "9Z")
        item = _value_item(editor, "project_code")
        refreshes("object", lambda: _object(panel) is editor and editor.dirty and editor.tree.set(item, "value") == "9Z")
        panel._obj_mode = False
        with _Answer(True):
            _pick(root, panel, paths["text"])
        text = panel._textw
        _type(root, panel, "1.0", "# edited\n")
        refreshes("text", lambda: panel._textw is text and text.get("1.0", "2.0") == "# edited\n"
                  and panel._unsaved_changes())
        with _Answer(True):
            _pick(root, panel, paths["templates"])
        mode, text = panel._template, panel._textw
        _type(root, panel, "1.0", "# edited\n")
        refreshes("template", lambda: panel._template is mode and panel._textw is text
                  and text.get("1.0", "2.0") == "# edited\n" and panel._unsaved_changes())
    finally:
        _end(root, project)


def test_the_text_object_toggle_asks_both_ways():
    """Gap 1: the Text <-> Object explorer toggle dropped the text pane's unsaved edits (the template mode's
    included) without a question. It asks now, both ways: No leaves the toggle on the shown side with the same
    viewer and its edit, Yes switches (the edit never written). A clean side switches without a question, and
    the side already shown changes nothing - it used to reload the file, edit and all."""
    begun = _begin()
    if begun is None:
        return
    root, project, paths, panel = begun
    try:
        panel._obj_mode = False
        _pick(root, panel, paths["yaml"])
        text = panel._textw
        with _Answer(False) as never:
            _toggle(root, panel, "Text")                      # the side already shown, clean
            _type(root, panel, "1.0", "# edited\n")
            _toggle(root, panel, "Text")                      # …and with an unsaved edit
        eq(never.asked, [], "the side already shown asks nothing")
        ok(panel._textw is text and text.get("1.0", "2.0") == "# edited\n", "…and reloads nothing: the edit stays")
        with _Answer(False) as no:
            _toggle(root, panel, "Object explorer")
        eq(no.asked, _question(paths["yaml"]), "Text -> Object explorer over an edit asks")
        ok(panel._textw is text and text.winfo_exists() and text.get("1.0", "2.0") == "# edited\n",
           "No keeps the same text pane with its edit")
        eq((_object(panel), panel._obj_mode, _shown_side(panel)), (None, False, ["Text"]),
           "…no Object explorer; the toggle still on Text")
        with _Answer(True) as yes:
            _toggle(root, panel, "Object explorer")
        eq(yes.asked, _question(paths["yaml"]), "asked again")
        ok(_object(panel) is not None and panel._obj_mode, "Yes shows the Object explorer")
        eq(_disk(paths["yaml"]), paths["disk"]["yaml"], "…the edit never written")

        editor = _commit_value(panel, "project_code", "9Z")
        with _Answer(False) as no:
            _toggle(root, panel, "Text")
        eq(no.asked, _question(paths["yaml"]), "Object explorer -> Text over a committed value asks")
        ok(_object(panel) is editor and editor.dirty and panel._obj_mode, "No keeps the same Object explorer, dirty")
        eq(_shown_side(panel), ["Object explorer"], "…the toggle still on it")
        with _Answer(True) as yes:
            _toggle(root, panel, "Text")
        eq((yes.asked, _object(panel), panel._obj_mode), (_question(paths["yaml"]), None, False), "Yes: the Text view")
        eq(_disk(paths["yaml"]), paths["disk"]["yaml"], "…the value never written")
        with _Answer(False) as never:
            _toggle(root, panel, "Object explorer")
            _toggle(root, panel, "Text")
        eq(never.asked, [], "a clean side switches both ways without a question")
        eq(_shown_side(panel), ["Text"], "…and did switch")

        _pick(root, panel, paths["templates"])               # the template mode (Text side)
        mode = panel._template
        ok(mode is not None, "the template mode")
        _type(root, panel, "1.0", "# edited\n")
        with _Answer(False) as no:
            _toggle(root, panel, "Object explorer")
        eq(no.asked, _question(paths["templates"]), "the template mode's edit asks too")
        ok(panel._template is mode and panel._textw.get("1.0", "2.0") == "# edited\n",
           "No keeps the same template mode with its edit")
        with _Answer(True):
            _toggle(root, panel, "Object explorer")
        ok(panel._template is None and _object(panel) is not None, "Yes: the Object explorer")
        eq(_disk(paths["templates"]).decode("utf-8").startswith("belt:"), True, "…the template edit never written")
    finally:
        _end(root, project)


def test_a_theme_switch_re_themes_in_place():
    """Gap 3: set_theme reloaded a shown CSV / xlsx - a dirty grid lost its cell edits without a question (and an
    xlsx fell back to its first sheet). A light/dark switch asks nothing and reloads nothing now: each viewer is
    the same widget afterwards, its unsaved edit and its view kept, in the new theme."""
    begun = _begin()
    if begun is None:
        return
    root, project, paths, panel = begun
    try:
        _pick(root, panel, paths["csv"])
        grid = _grid(panel)
        grid._commit_cell(0, 1, "99")
        grid.add_filter({"col": 0, "text": "e"})               # the view: a column filter (both rows pass)…
        grid._click_col, grid._drag = 1, None                  # …and a header click on qty: sorted ascending
        grid._header_release(None)
        eq((grid._sort, grid._view), ((1, "asc"), [1, 0]), "(the view: sorted by qty - 2 before 99)")
        with _Answer(False) as never:
            panel.set_theme("light")
            root.update()
        eq(never.asked, [], "a theme switch asks nothing")
        ok(_grid(panel) is grid and panel._csv_dirty and grid._rows[0][1] == "99", "the same grid with its edit")
        eq((grid.active_filters(), grid._sort, grid._view), ([{"col": 0, "text": "e"}], (1, "asc"), [1, 0]),
           "…its filter, sort and view kept")
        eq((grid._mode, str(grid.body.cget("bg"))), ("light", theme.TOKENS["light"]["field"]), "…in the new theme")
        _button(panel.editor, "Save").invoke()
        eq(_disk(paths["csv"]), b"name,qty\r\nbelt,99\r\npec,2\r\n", "…and Save writes the edit it kept")
        ok(not panel._csv_dirty, "…saved: clean")

        _pick(root, panel, paths["big"])                       # a grid scrolled half-way (refute round 2: the 2-row
        grid = _grid(panel)                                    # table cannot scroll - a re-theme through the view's
        grid._commit_cell(0, 1, "99")                          # refresh, which scrolls home, passed)
        grid.body.yview_moveto(0.5)
        root.update()
        scrolled = grid.body.yview()
        ok(scrolled[0] > 0.4, f"(scrolled: {scrolled})")
        panel.set_theme("dark")
        root.update()
        ok(_grid(panel) is grid and panel._csv_dirty, "the scrolled grid: the same, dirty")
        eq((grid.body.yview(), grid._mode), (scrolled, "dark"), "…its scroll kept, re-themed")

        with _Answer(True) as yes:                              # leaving the edited grid asks (its edit let go)
            _pick(root, panel, paths["xlsx"])
        eq(yes.asked, _question(paths["big"]), "(leaving the edited grid asked)")
        box = _widgets(panel.editor, ttk.Combobox)[0]
        box.set("second")
        box.event_generate("<<ComboboxSelected>>")
        root.update()
        grid = _grid(panel)
        eq(grid._columns, ["x", "y", "z"], "(the second sheet shown)")
        panel.set_theme("light")
        root.update()
        ok(_grid(panel) is grid, "an xlsx grid is the same widget")
        eq((box.get(), grid._columns, grid._mode), ("second", ["x", "y", "z"], "light"), "…still on its sheet, re-themed")
        box.set("first")                                       # a sheet picked AFTER the switch comes up in its theme
        box.event_generate("<<ComboboxSelected>>")
        root.update()
        grid = _grid(panel)
        eq((grid._columns, grid._mode, str(grid.body.cget("bg"))), (["a", "b"], "light", theme.TOKENS["light"]["field"]),
           "a sheet picked after the switch: in the new theme")

        panel._obj_mode = True                                 # (every viewer below is built in one theme and
        _pick(root, panel, paths["yaml"])                      # switched to the OTHER - a no-op switch proves nothing)
        editor = _commit_value(panel, "project_code", "9Z")
        light, dark = theme.TOKENS["light"], theme.TOKENS["dark"]

        def object_colours():
            return (str(editor.tree.tag_configure("z0", "background")), str(editor.tree.tag_configure("z1", "background")),
                    [str(d.cget("bg")) for d in editor._dividers])
        eq(object_colours(), (light["field"], light["field_alt"], [light["grid_line"]] * 2), "(the Object explorer, light)")
        with _Answer(False) as never:
            panel.set_theme("dark")
            root.update()
        eq(never.asked, [], "the Object explorer: no question")
        ok(_object(panel) is editor and editor.dirty, "the same Object explorer with its edit")
        eq(object_colours(), (dark["field"], dark["field_alt"], [dark["grid_line"]] * 2),
           "…its rows and dividers in the new theme")

        panel._obj_mode = False
        with _Answer(True):
            _pick(root, panel, paths["text"])
        _type(root, panel, "1.0", "X")
        text = panel._textw
        lang = _widgets(panel.editor, ttk.Combobox)[0]          # a .txt the highlighter does not know by name,
        lang.set("yaml")                                         # coloured as yaml from the Lang box
        lang.event_generate("<<ComboboxSelected>>")
        root.update()
        eq(str(text.tag_cget("hl_key", "foreground")), highlight.COLORS["hl_key"][0], "(the Lang box's yaml, dark)")
        panel.set_theme("light")
        root.update()
        ok(panel._textw is text and text.get("1.0", "1.1") == "X" and panel._unsaved_changes(),
           "the text pane: the same widget with its edit")
        eq(str(text.cget("background")), theme.bg_for("light"), "…re-themed")
        eq(str(text.tag_cget("hl_key", "foreground")), highlight.COLORS["hl_key"][1],
           "…its highlight too - a language picked in the Lang box included")
        with _Answer(True):
            _pick(root, panel, paths["templates"])
        mode = panel._template
        _type(root, panel, "1.0", "# edited\n")
        eq(str(panel._textw.tag_cget("tp_directive", "foreground")), template_doc.TAG_COLORS["tp_directive"][1],
           "(the template layer, light)")
        panel.set_theme("dark")
        root.update()
        ok(panel._template is mode and panel._textw.get("1.0", "2.0") == "# edited\n" and panel._unsaved_changes(),
           "the template mode: the same, with its edit")
        eq((str(panel._textw.cget("background")), str(panel._textw.tag_cget("tp_directive", "foreground")),
            str(panel._textw.tag_cget("hl_key", "foreground")), str(mode.preview.cget("background"))),
           (theme.bg_for("dark"), template_doc.TAG_COLORS["tp_directive"][0], highlight.COLORS["hl_key"][0],
            theme.bg_for("dark")),
           "…re-themed: the pane itself, its template layer, the language under it and its preview")
    finally:
        _end(root, project)


def test_back_to_the_saved_text_is_clean():
    """Gap 4 + the spike's fifth: the text pane is modified exactly while its text differs from the saved one. A
    Ctrl+Z before any edit changes nothing (it undid the LOAD: the pane emptied, marked modified, Save one click
    away); an edit undone, redone or retyped back to the saved text is clean for the guard at once and for the
    mark after the pause; an undo past a Save is modified - the saved text moved."""
    begun = _begin()
    if begun is None:
        return
    root, project, paths, panel = begun
    try:
        _pick(root, panel, paths["text"])
        text = panel._textw
        save = _button(panel.editor, "Save")
        _event(root, panel, "<<Undo>>")
        eq(text.get("1.0", "end-1c"), _NOTES, "a Ctrl+Z before any edit: the text as loaded")
        ok(not panel._unsaved_changes() and _mark(panel) == "" and save.instate(["disabled"]), "…and clean")
        _type(root, panel, "1.0", "X")
        ok(panel._unsaved_changes() and _mark(panel) == "● modified" and not save.instate(["disabled"]),
           "an edit: modified")
        _event(root, panel, "<<Undo>>")
        eq(text.get("1.0", "end-1c"), _NOTES, "undone")
        ok(not panel._unsaved_changes(), "…clean for the guard at once")
        ok(_pump(root, lambda: _mark(panel) == ""), "…and the mark clears after the pause")
        ok(save.instate(["disabled"]), "…Save disabled")
        _event(root, panel, "<<Redo>>")
        ok(text.get("1.0", "1.1") == "X" and panel._unsaved_changes() and _mark(panel) == "● modified", "redone: modified")
        text.delete("1.0", "1.1")                             # deleted back - what a cut of the 'X' does to the text
        root.update()
        ok(not panel._unsaved_changes(), "deleted back to the saved text: clean")
        text.delete("1.0", "1.1")
        root.update()
        ok(panel._unsaved_changes(), "a character removed: modified")
        _type(root, panel, "1.0", "l")                       # …and retyped
        ok(not panel._unsaved_changes() and _pump(root, lambda: _mark(panel) == ""), "retyped: clean again")
        with _Answer(False) as never:
            _pick(root, panel, paths["csv"])
            _pick(root, panel, paths["text"])
        eq(never.asked, [], "clean after the round trips: another file asks nothing")

        text = panel._textw
        _type(root, panel, "end-1c", "Y")
        _button(panel.editor, "Save").invoke()
        root.update()
        eq(_disk(paths["text"]), (_NOTES + "Y").encode(), "saved")
        ok(not panel._unsaved_changes() and _mark(panel) == "", "…clean")
        _event(root, panel, "<<Undo>>")
        eq(text.get("1.0", "end-1c"), _NOTES, "an undo past the Save")
        ok(panel._unsaved_changes(), "…is modified: the saved text moved")
        ok(not _pump(root, lambda: _mark(panel) == "", 0.8), "…the mark stays")
        _event(root, panel, "<<Redo>>")
        ok(not panel._unsaved_changes() and _pump(root, lambda: _mark(panel) == ""), "redone to the saved text: clean")

        _pick(root, panel, paths["templates"])
        loaded = _disk(paths["templates"]).decode("utf-8").replace("\r\n", "\n")   # the pane holds \n newlines
        _event(root, panel, "<<Undo>>")
        eq(panel._textw.get("1.0", "end-1c"), loaded, "the template mode: a Ctrl+Z before any edit changes nothing")
        ok(not panel._unsaved_changes(), "…clean")
        _type(root, panel, "1.0", "# edited\n")
        _event(root, panel, "<<Undo>>")
        ok(panel._textw.get("1.0", "end-1c") == loaded and not panel._unsaved_changes(), "…an edit undone: clean")

        panel._load(_SHIPPED)                                # a read-only pane (the shipped templates.yaml)
        root.update()
        shipped = _disk(_SHIPPED).decode("utf-8").replace("\r\n", "\n")
        _event(root, panel, "<<Undo>>")
        eq(panel._textw.get("1.0", "end-1c"), shipped, "a read-only pane: a Ctrl+Z changes nothing either")
    finally:
        _end(root, project)


def test_a_pane_that_goes_leaves_no_timer():
    """Refute round 3's side finding: an edit arms the text pane's debounced re-check (the mark) and re-highlight;
    a pane that went within their delay - another file picked, Revert, the Text -> Object toggle - left them
    pending, and they fired into its deleted Tcl command (`invalid command name "...recheck"`, swallowed by
    tkinter's no-op `tkerror`). They go with the pane now, however it goes - the panel itself destroyed (what
    closing the App does to it) included; the template mode's own timers still go too, what follows the pane comes
    up (refute round 4: `_load` turns an exception raised while the pane is destroyed into a 'could not open'
    placeholder no recorder sees), and a pane whose timers already ran goes as cleanly: no background error, no
    callback raising."""
    begun = _begin()
    if begun is None:
        return
    root, project, paths, panel = begun
    errors = []                                              # Tcl's background errors + the callbacks' own exceptions
    root.tk.call("interp", "bgerror", "", root.register(lambda message, *_options: errors.append(message)))
    root.report_callback_exception = lambda kind, value, _tb: errors.append(f"{kind.__name__}: {value}")
    try:
        def leaves(name, path, armed, leave, follows):
            _pick(root, panel, path)
            _type(root, panel, "1.0", "# edited\n")
            eq(_timers(root), armed, f"{name}: (the edit armed them)")
            with _Answer(True):                              # (where leaving asks - the pane holds the edit)
                leave()
            eq([job for job in _timers(root) if job[0] in ("recheck", "rehighlight") or not job[1]], [],
               f"{name}: the pane gone - none of its timers left, none firing into a deleted command")
            ok(follows(), f"{name}: …what follows it shown - not a 'could not open' placeholder")

        def shown(path, viewer):
            return lambda: os.path.normcase(panel._cur) == os.path.normcase(path) and viewer()

        def a_grid():
            return len(_widgets(panel.editor, datagrid.DataGrid)) == 1

        def reread():                                        # Revert: the file's own text, the edit gone
            loaded = paths["disk"]["yaml"].decode("utf-8").replace("\r\n", "\n")
            return panel._textw is not None and panel._textw.get("1.0", "end-1c") == loaded

        both = [("recheck", True), ("rehighlight", True)]
        panel._obj_mode = False
        _pick(root, panel, paths["yaml"])
        _type(root, panel, "1.0", "# edited\n")
        ok(_pump(root, lambda: _timers(root) == []), "(a pause after the edit: both ran)")
        with _Answer(True):
            _pick(root, panel, paths["xlsx"])                # …then the pane goes, nothing pending
        leaves("another file", paths["yaml"], both, lambda: _pick(root, panel, paths["xlsx"]),
               shown(paths["xlsx"], a_grid))
        leaves("Revert", paths["yaml"], both, lambda: (_button(panel.editor, "Revert").invoke(), root.update()),
               shown(paths["yaml"], reread))
        leaves("the toggle", paths["yaml"], both, lambda: _toggle(root, panel, "Object explorer"),
               shown(paths["yaml"], lambda: _object(panel) is not None))
        panel._obj_mode = False
        leaves("the template mode", paths["templates"], [("_debounced", True), ("_poll", True), ("recheck", True)],
               lambda: _pick(root, panel, paths["csv"]), shown(paths["csv"], a_grid))
        leaves("the panel destroyed", paths["yaml"], both, panel.destroy, lambda: not panel.winfo_exists())
        _pump(root, lambda: False, 0.5)                      # past every delay (250 ms at most)
        eq(errors, [], "no background error, no callback raised")
    finally:
        _end(root, project)


def test_grid_and_object_explorer_stay_modified_until_save():
    """The recorded boundary on the safe side: the CSV grid and the Object explorer stay modified from their first
    committed change until Save - a value typed back to what the file holds still asks (a needless question,
    never a lost edit); Save makes them clean."""
    begun = _begin()
    if begun is None:
        return
    root, project, paths, panel = begun
    try:
        _pick(root, panel, paths["csv"])
        grid = _grid(panel)
        grid._commit_cell(0, 1, "99")
        grid._commit_cell(0, 1, "1")                          # typed back to the file's value
        ok(panel._csv_dirty and panel._unsaved_changes(), "the grid: still modified")
        with _Answer(False) as no:
            _pick(root, panel, paths["text"])
        eq(no.asked, _question(paths["csv"]), "…so another file asks")
        _button(panel.editor, "Save").invoke()
        root.update()
        ok(not panel._unsaved_changes(), "saved: clean")
        eq(_disk(paths["csv"]), _CSV.encode(), "(the same table written back)")
        panel._obj_mode = True
        _pick(root, panel, paths["yaml"])
        editor = _commit_value(panel, "project_code", "9Z")
        _commit_value(panel, "project_code", "8X")            # typed back
        ok(editor.dirty and panel._unsaved_changes(), "the Object explorer: still modified")
        with _Answer(False) as no:
            _pick(root, panel, paths["text"])
        eq(no.asked, _question(paths["yaml"]), "…so another file asks")
        _button(editor, "Save").invoke()
        root.update()
        ok(not editor.dirty and not panel._unsaved_changes(), "saved: clean")
    finally:
        _end(root, project)


def test_a_refused_save_is_no_save():
    """Refute round 2: a Save the OS refuses (the file held open - Excel does that to a CSV) is no Save. The text
    pane, the CSV grid and the Object explorer keep the file as it was, stay modified (the mark shown), and
    leaving them still asks - a viewer marked clean before its write succeeded let the edit go unasked. Once the
    writer works again, Save saves. (The writers refuse as the OS does: PermissionError.)"""
    begun = _begin()
    if begun is None:
        return
    root, project, paths, panel = begun
    refused = _Patched((files_view, "write_text_file", _refuse), (files_view, "write_csv_rows", _refuse),
                       (objectview, "dump_document", _refuse))
    try:
        statuses = []
        panel.on_status = statuses.append

        def refused_then_asks(name, path, save_button, still):
            with refused:
                save_button.invoke()
                root.update()
            ok(statuses and statuses[-1].startswith("save failed"), f"{name}: the refusal reported ({statuses[-1:]})")
            eq(_disk(path), paths["disk"][name], f"{name}: the file as it was")
            ok(panel._unsaved_changes() and still(), f"{name}: still modified")
            with _Answer(False) as no:
                _pick(root, panel, paths["xlsx"])
            eq(no.asked, _question(path), f"{name}: leaving it still asks")
            ok(still(), f"{name}: …No keeps the edit")
            save_button.invoke()                              # the writer works again
            root.update()
            ok(not panel._unsaved_changes(), f"{name}: then Save saves")

        _pick(root, panel, paths["text"])
        _type(root, panel, "1.0", "X")
        text = panel._textw
        refused_then_asks("text", paths["text"], _button(panel.editor, "Save"),
                          lambda: panel._textw is text and text.get("1.0", "1.1") == "X" and _mark(panel) == "● modified")
        eq(_disk(paths["text"]), ("X" + _NOTES).encode(), "text: written once the writer works")
        with _Answer(True):
            _pick(root, panel, paths["csv"])
        grid = _grid(panel)
        grid._commit_cell(0, 1, "99")
        refused_then_asks("csv", paths["csv"], _button(panel.editor, "Save"),
                          lambda: _grid(panel) is grid and panel._csv_dirty and grid._rows[0][1] == "99")
        panel._obj_mode = True
        with _Answer(True):
            _pick(root, panel, paths["yaml"])
        editor = _commit_value(panel, "project_code", "9Z")
        refused_then_asks("yaml", paths["yaml"], _button(editor, "Save"),
                          lambda: _object(panel) is editor and editor.dirty)
    finally:
        _end(root, project)


def test_every_object_explorer_edit_counts():
    """Refute round 2: the Object explorer has three ways to edit - a value committed in place, a neighbour added
    (right-click 'Add element': a new mapping key, a duplicated list member) and a path chosen with its '…' picker -
    and each one is an unsaved change the guard sees: leaving asks, No keeps the editor with the edit."""
    begun = _begin()
    if begun is None:
        return
    root, project, paths, panel = begun
    try:
        panel._obj_mode = True
        _pick(root, panel, paths["doc"])
        editor = _object(panel)
        chosen = os.path.join(os.path.dirname(paths["doc"]), "notes.txt")
        edits = (("a mapping key added", lambda: editor._add_neighbor(_value_item(editor, "input_path")),
                  lambda: "new_key" in editor._doc),
                 ("a list member added", lambda: editor._add_neighbor(_value_item(editor, 0)),
                  lambda: list(editor._doc["items"]) == ["a", "a"]),
                 ("a path picked", lambda: editor._pick(_value_item(editor, "input_path"), ("input_path",), "file"),
                  lambda: editor._doc["input_path"] == "notes.txt"))
        with _Patched((simpledialog, "askstring", lambda *_a, **_k: "new_key"),
                      (filedialog, "askopenfilename", lambda *_a, **_k: chosen)):
            for name, edit, done in edits:
                ok(not editor.dirty and not panel._unsaved_changes(), f"{name}: (clean before)")
                edit()
                ok(done() and editor.dirty, f"{name}: an unsaved change")
                with _Answer(False) as no:
                    _pick(root, panel, paths["text"])
                eq(no.asked, _question(paths["doc"]), f"{name}: leaving asks")
                ok(_object(panel) is editor and editor.dirty and done(), f"{name}: No keeps the editor with the edit")
                _button(editor, "Revert").invoke()            # clean again for the next way
                root.update()
        eq(_disk(paths["doc"]), paths["disk"]["doc"], "nothing written")
    finally:
        _end(root, project)


def test_revert_is_the_discard_itself():
    """The deliberate boundary: Revert re-reads the file without a question - the text pane's, the CSV grid's
    and the Object explorer's own."""
    begun = _begin()
    if begun is None:
        return
    root, project, paths, panel = begun
    try:
        _pick(root, panel, paths["text"])
        _type(root, panel, "1.0", "X")
        with _Answer(False) as never:
            _button(panel.editor, "Revert").invoke()
            root.update()
            ok(panel._textw.get("1.0", "end-1c") == _NOTES and not panel._unsaved_changes(), "the text pane reverted")
            _pick(root, panel, paths["csv"])
            _grid(panel)._commit_cell(0, 1, "99")
            _button(panel.editor, "Revert").invoke()
            root.update()
            ok(_grid(panel)._rows[0][1] == "1" and not panel._csv_dirty, "the CSV grid reverted")
            panel._obj_mode = True
            _pick(root, panel, paths["yaml"])
            editor = _commit_value(panel, "project_code", "9Z")
            _button(editor, "Revert").invoke()
            root.update()
            item = _value_item(editor, "project_code")
            ok(not editor.dirty and editor.tree.set(item, "value") == "8X", "the Object explorer reverted")
        eq(never.asked, [], "no Revert asks")
        eq((_disk(paths["text"]), _disk(paths["csv"]), _disk(paths["yaml"])),
           (_NOTES.encode(), paths["disk"]["csv"], paths["disk"]["yaml"]), "nothing written")
    finally:
        _end(root, project)


def test_closing_the_app_asks():
    """Closing the app over an unsaved Files-tab edit asks too: No keeps the app open - nothing persisted,
    nothing destroyed; Yes closes it; a clean Files tab closes without a question. The App's real `_on_close`
    over a real FilesPanel - the rest of the App stubbed (building one would re-open the user's last project and
    persist into the live app_config). Headless too: the window manager's close - the title-bar X - IS that
    `_on_close` (refute round 1: the stubbed call alone stayed green with the protocol bound elsewhere)."""
    import inspect
    from pipeline5.workbench.app_main import App
    eq(re.findall(r'root\.protocol\("WM_DELETE_WINDOW", self\.(\w+)\)', inspect.getsource(App.__init__)), ["_on_close"],
       "the App binds the window manager's close to _on_close, once, at construction")
    begun = _begin()
    if begun is None:
        return
    root, project, paths, panel = begun
    calls = []
    window = types.SimpleNamespace(winfo_width=lambda: 900, winfo_height=lambda: 700,
                                   destroy=lambda: calls.append("destroyed"))
    app = types.SimpleNamespace(files=panel, root=window, _disable_log_sink=lambda: calls.append("tee closed"))
    persist = config.save_app_window_size
    config.save_app_window_size = lambda width, height: calls.append(("size saved", width, height))
    closed = [("size saved", 900, 700), "tee closed", "destroyed"]
    try:
        panel._obj_mode = True
        _pick(root, panel, paths["yaml"])
        _commit_value(panel, "project_code", "9Z")
        with _Answer(False) as no:
            App._on_close(app)
        eq((no.asked, calls), (_question(paths["yaml"]), []), "No: the app stays open - nothing persisted")
        ok(_object(panel).dirty, "…the edit still there")
        with _Answer(True) as yes:
            App._on_close(app)
        eq((yes.asked, calls), (_question(paths["yaml"]), closed), "Yes: the app closes")
        eq(_disk(paths["yaml"]), paths["disk"]["yaml"], "…the edit never written")
        del calls[:]
        _button(_object(panel), "Revert").invoke()
        with _Answer(False) as never:
            App._on_close(app)
        eq((never.asked, calls), ([], closed), "a clean Files tab closes without a question")
    finally:
        config.save_app_window_size = persist
        _end(root, project)


def test_the_project_copy_jump_asks():
    """The project-copy jump opens its target directly when the tree does not list it - through the same
    question. (It starts from a shipped, read-only file, which holds no edit today; the one guard keeps it so.)"""
    begun = _begin()
    if begun is None:
        return
    root, project, paths, panel = begun
    try:
        outside = os.path.join(project.name, "elsewhere.txt")
        with open(outside, "w", encoding="utf-8") as handle:
            handle.write("not listed\n")
        _pick(root, panel, paths["text"])
        text = panel._textw
        _type(root, panel, "1.0", "X")
        with _Answer(False) as no:
            panel._reveal(outside)
            root.update()
        eq(no.asked, _question(paths["text"]), "the jump asks")
        ok(panel._textw is text and text.get("1.0", "1.1") == "X", "No keeps the edited pane")
        with _Answer(True):
            panel._reveal(outside)
            root.update()
        eq(os.path.normcase(panel._cur), os.path.normcase(outside), "Yes: the target shown")
        eq(_disk(paths["text"]), _NOTES.encode(), "…the edit never written")
    finally:
        _end(root, project)


def test_an_open_cell_editor_is_not_an_edit():
    """The other deliberate boundary: a cell or value editor still open (no Enter yet) is not an edit - leaving
    it cancels it, as Escape does - so picking another file asks nothing, and nothing typed there is written."""
    begun = _begin()
    if begun is None:
        return
    root, project, paths, panel = begun
    try:
        _pick(root, panel, paths["csv"])
        grid = _grid(panel)
        grid._cell_dclick(types.SimpleNamespace(x=5, y=2))   # a double-click on the first data cell
        ok(grid._editbox is not None, "(the cell editor is open)")
        grid._editbox.insert("end", " typed")
        panel._obj_mode = True
        with _Answer(False) as never:
            _pick(root, panel, paths["yaml"])
            editor = _object(panel)
            editor._open_edit(_value_item(editor, "project_code"))
            ok(editor._editbox is not None, "(the value editor is open)")
            editor._editbox.insert("end", " typed")
            _pick(root, panel, paths["text"])
        eq(never.asked, [], "an open cell / value editor asks nothing")
        eq((_disk(paths["csv"]), _disk(paths["yaml"])), (paths["disk"]["csv"], paths["disk"]["yaml"]), "…nothing typed there written")
    finally:
        _end(root, project)


if __name__ == "__main__":
    import sys
    sys.exit(run("gui_files_discard", [
        ("another_file_asks_for_every_viewer", test_another_file_asks_for_every_viewer),
        ("a_refresh_keeps_every_viewer", test_a_refresh_keeps_every_viewer),
        ("the_text_object_toggle_asks_both_ways", test_the_text_object_toggle_asks_both_ways),
        ("a_theme_switch_re_themes_in_place", test_a_theme_switch_re_themes_in_place),
        ("back_to_the_saved_text_is_clean", test_back_to_the_saved_text_is_clean),
        ("a_pane_that_goes_leaves_no_timer", test_a_pane_that_goes_leaves_no_timer),
        ("grid_and_object_explorer_stay_modified_until_save", test_grid_and_object_explorer_stay_modified_until_save),
        ("a_refused_save_is_no_save", test_a_refused_save_is_no_save),
        ("every_object_explorer_edit_counts", test_every_object_explorer_edit_counts),
        ("revert_is_the_discard_itself", test_revert_is_the_discard_itself),
        ("closing_the_app_asks", test_closing_the_app_asks),
        ("the_project_copy_jump_asks", test_the_project_copy_jump_asks),
        ("an_open_cell_editor_is_not_an_edit", test_an_open_cell_editor_is_not_an_edit),
    ]))
