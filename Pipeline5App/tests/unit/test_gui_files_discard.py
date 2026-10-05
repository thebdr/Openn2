"""C-026 - the Files tab never drops an unsaved edit without asking - driven through the REAL FilesPanel on an
off-screen Tk root (SKIPPED where no display exists), `tkinter.messagebox.askyesno` answering both ways. Each
viewer that edits - the text pane (the template mode's included), the CSV grid, the Object explorer - is made
dirty for real, then every path that would replace or close it runs: another file picked in the tree, the
Text <-> Object explorer toggle, the project-copy jump, the App's close. A light/dark switch re-themes in place;
the text pane is clean again once its text is back to the saved one; Revert is the deliberate discard."""
import os
import re
import tempfile
import tkinter.messagebox as messagebox
import types
from tkinter import ttk

from openpyxl import Workbook

from _harness import run, eq, ok
from pipeline5 import config
from pipeline5.workbench import datagrid, object_editor, template_doc, theme
from pipeline5.workbench import syntax_highlight as highlight
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


def _begin():
    """(root, tempdir, paths, panel) - the panel lists the project's config_project; None without a display.
    `paths["disk"]` keeps every fixture file's bytes as written (_project writes in the platform's newlines)."""
    root = _tk()
    if root is None:
        return None
    template_doc.Session = _session                          # the template mode's Database: synthetic, no staging
    project = tempfile.TemporaryDirectory()
    paths = _fixture(project.name)
    paths["disk"] = {key: _disk(path) for key, path in list(paths.items())}
    config.use_project(project.name)
    return root, project, paths, _panel(root, project.name)


def _end(root, project) -> None:
    template_doc.Session = _REAL_SESSION
    config.use_project(None)
    _done(root)
    project.cleanup()


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

        _pick(root, panel, paths["templates"])               # a refresh (after a run, a project / system
        mode, text = panel._template, panel._textw           # switch) keeps the shown viewer: the builder
        _type(root, panel, "1.0", "# edited\n")              # re-reads its rules + data, never the text
        with _Answer(False) as never:
            panel.refresh()
            _pump(root, lambda: False, 1.0)
        eq(never.asked, [], "a refresh asks nothing")
        ok(panel._template is mode and panel._textw is text and text.get("1.0", "2.0") == "# edited\n"
           and panel._unsaved_changes(), "…and keeps the edited template mode, still modified")
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

        _pick(root, panel, paths["xlsx"])
        box = _widgets(panel.editor, ttk.Combobox)[0]
        box.set("second")
        box.event_generate("<<ComboboxSelected>>")
        root.update()
        grid = _grid(panel)
        eq(grid._columns, ["x", "y", "z"], "(the second sheet shown)")
        panel.set_theme("dark")
        root.update()
        ok(_grid(panel) is grid, "an xlsx grid is the same widget")
        eq((box.get(), grid._columns, grid._mode), ("second", ["x", "y", "z"], "dark"), "…still on its sheet, re-themed")

        panel._obj_mode = True
        _pick(root, panel, paths["yaml"])
        editor = _commit_value(panel, "project_code", "9Z")
        with _Answer(False) as never:
            panel.set_theme("light")
            root.update()
        eq(never.asked, [], "the Object explorer: no question")
        ok(_object(panel) is editor and editor.dirty, "the same Object explorer with its edit")
        light = theme.TOKENS["light"]
        eq((str(editor.tree.tag_configure("z0", "background")), str(editor.tree.tag_configure("z1", "background")),
            [str(d.cget("bg")) for d in editor._dividers]),
           (light["field"], light["field_alt"], [light["grid_line"]] * 2), "…its rows and dividers in the new theme")

        panel._obj_mode = False
        with _Answer(True):
            _pick(root, panel, paths["text"])
        _type(root, panel, "1.0", "X")
        text = panel._textw
        lang = _widgets(panel.editor, ttk.Combobox)[0]          # a .txt the highlighter does not know by name,
        lang.set("yaml")                                         # coloured as yaml from the Lang box
        lang.event_generate("<<ComboboxSelected>>")
        root.update()
        eq(str(text.tag_cget("hl_key", "foreground")), highlight.COLORS["hl_key"][1], "(the Lang box's yaml, light)")
        panel.set_theme("dark")
        root.update()
        ok(panel._textw is text and text.get("1.0", "1.1") == "X" and panel._unsaved_changes(),
           "the text pane: the same widget with its edit")
        eq(str(text.cget("background")), theme.bg_for("dark"), "…re-themed")
        eq(str(text.tag_cget("hl_key", "foreground")), highlight.COLORS["hl_key"][0],
           "…its highlight too - a language picked in the Lang box included")
        with _Answer(True):
            _pick(root, panel, paths["templates"])
        mode = panel._template
        _type(root, panel, "1.0", "# edited\n")
        panel.set_theme("light")
        root.update()
        ok(panel._template is mode and panel._textw.get("1.0", "2.0") == "# edited\n" and panel._unsaved_changes(),
           "the template mode: the same, with its edit")
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
    persist into the live app_config)."""
    from pipeline5.workbench.app_main import App
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
        ("the_text_object_toggle_asks_both_ways", test_the_text_object_toggle_asks_both_ways),
        ("a_theme_switch_re_themes_in_place", test_a_theme_switch_re_themes_in_place),
        ("back_to_the_saved_text_is_clean", test_back_to_the_saved_text_is_clean),
        ("grid_and_object_explorer_stay_modified_until_save", test_grid_and_object_explorer_stay_modified_until_save),
        ("revert_is_the_discard_itself", test_revert_is_the_discard_itself),
        ("closing_the_app_asks", test_closing_the_app_asks),
        ("the_project_copy_jump_asks", test_the_project_copy_jump_asks),
        ("an_open_cell_editor_is_not_an_edit", test_an_open_cell_editor_is_not_an_edit),
    ]))
