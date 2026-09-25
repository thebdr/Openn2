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


class _Session(template_doc.Session):
    """The real Session, its hook Database synthetic (no staging in a unit test)."""
    def database(self, hook):
        return _signals() if hook == "after_300" else None


def _tk():
    try:
        import tkinter as tk
        root = tk.Tk()
    except Exception as error:  # noqa: BLE001 - no display: the GUI half is skipped, not failed
        print(f"  SKIP  (no Tk display: {error})")
        return None
    root.geometry("1000x700+-3000+-3000")                  # mapped (bbox works) but off-screen
    return root


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


def _tagged(text, tag):
    ranges = text.tag_ranges(tag)
    return [text.get(ranges[i], ranges[i + 1]) for i in range(0, len(ranges), 2)]


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


def test_template_mode_in_the_files_panel():
    """The real panel: the template mode's layers, a rule + its preview, a lint squiggle and its
    problem row, a completion popup accepted into the text."""
    root = _tk()
    if root is None:
        return
    original = template_doc.Session
    template_doc.Session = _Session
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
            eq(mode.problems.get_children(), (), "no rule chosen: the document alone is clean")
            ok("Choose a rule" in mode.preview.get("1.0", "end"), "the preview invites a rule")
            mode.rule_box.current(1)
            mode.on_rule()
            eq(str(mode.row_box.cget("to")), "1.0", "the rule's source rows (2) at its hook")
            preview = mode.preview.get("1.0", "end-1c")
            ok(preview.startswith("APPEND to ") and preview.endswith("REGION B1\n  PEC(P1);\nEND_REGION"),
               f"one fire for row 0: {preview!r}")
            text.insert("4.0", "  X {$r.tagg}\n")            # a loop-column typo inside the @for
            mode.refresh()
            rows = [mode.problems.item(i, "values") for i in mode.problems.get_children()]
            ok(any("tagg" in str(values) for values in rows), f"the problem row: {rows}")
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
        template_doc.Session = original
        config.use_project(None)
        root.destroy()


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
        root.destroy()


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
            shipped_csv = os.path.join(SYSTEM.config_root, "chain_reactions", "reactions.csv")
            panel._load(shipped_csv)
            root.update()
            eq([grid._editable for grid in _widgets(panel.editor, datagrid.DataGrid)], [False],
               "the shipped CSV grid is read-only")
            ok("Open project copy" in _buttons(panel.editor) and "Save" not in _buttons(panel.editor),
               f"…the project already has its copy: 'Open project copy', no Save ({_buttons(panel.editor)})")
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
        root.destroy()


if __name__ == "__main__":
    import sys
    sys.exit(run("gui_template_mode", [
        ("project_copy_helpers", test_project_copy_helpers),
        ("template_mode_in_the_files_panel", test_template_mode_in_the_files_panel),
        ("the_shipped_file_is_read_only_until_copied", test_the_shipped_file_is_read_only_until_copied),
        ("every_viewer_keeps_the_shipped_config_read_only", test_every_viewer_keeps_the_shipped_config_read_only),
    ]))
