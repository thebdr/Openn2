"""The TIA Portal version as a project setting (C-049): siemens_s7/tia_version.py (the spellings, the builtin
fallback, the stamp), the workspace header's `tia`, the System's project option and the New-project create
path (project_manager.create_project options), and PL5's SUPPORTED list against OP5's Openness range."""
import os
import re
import tempfile

from _harness import run, eq, ok, raises
from pipeline5 import config
from pipeline5.project import project_manager as project
from pipeline5.systems.plc_based.siemens_s7 import openn_header as header
from pipeline5.systems.plc_based.siemens_s7 import tia_version
from pipeline5.systems.plc_based.siemens_s7.safety.system import SYSTEM

_OPENNESS_SETUP = os.path.join(os.path.dirname(__file__), "..", "..", "..", "Openn5App", "03_ApiManager",
                               "OpennessSetup.cs")


def _with_temp_localappdata(fn):
    with tempfile.TemporaryDirectory() as d:
        old = os.environ.get("LOCALAPPDATA")
        os.environ["LOCALAPPDATA"] = d
        try:
            fn(d)
        finally:
            config.use_builtin()
            if old is None:
                os.environ.pop("LOCALAPPDATA", None)
            else:
                os.environ["LOCALAPPDATA"] = old


def test_normalize_spellings():
    for text in ("V20", "v20", "20", " V20 ", "V 20", 20):
        eq(tia_version.normalize(text), "V20", f"{text!r}")
    eq(tia_version.normalize("V18"), "V18")
    for bad in ("V17", "V21", "twenty", "", None, "V20.1"):
        raises(ValueError, lambda bad=bad: tia_version.normalize(bad))


def test_blank_or_missing_means_the_builtin_value():
    builtin_file = os.path.join(config.builtin_shared_config_dir(), "project_params.yaml")
    raw = config.load_params(builtin_file).get("tia_version")
    eq(tia_version.builtin(), tia_version.normalize(raw), "builtin() reads the builtin project_params.yaml")
    eq(tia_version.builtin(), "V20", "the builtin target is TIA V20 (the toolchain since 2026-10-27)")
    eq(tia_version.active({"tia_version": "V19"}), "V19", "the project's own value wins")
    eq(tia_version.active({"tia_version": ""}), tia_version.builtin(), "blank -> the builtin value")
    eq(tia_version.active({}), tia_version.builtin(), "a project made before the key -> the builtin value")
    raises(ValueError, lambda: tia_version.active({"tia_version": "V16"}))


def test_stamp_and_line():
    doc = '<?xml version="1.0"?>\r\n<Document>\r\n  <Engineering version="V18" />\r\n  <X />\r\n</Document>'
    out = tia_version.stamp(doc, "V20")
    ok('<Engineering version="V20" />' in out and "V18" not in out, "the template's stamp replaced")
    eq(out.replace("V20", "V18"), doc, "nothing else changes")
    eq(tia_version.stamp("<Document />", "V20"), "<Document />", "no stamp -> unchanged")
    eq(tia_version.engineering_line("V19"), '  <Engineering version="V19" />')


def test_workspace_header_carries_tia():
    fields = header.workspace_fields(run="r1", project="8XXX", plcs=["n1"], tia="V20")
    eq(fields.get("tia"), "V20")
    lines = header.directive_lines(fields)
    ok(lines.index("#! templates: Templates") < lines.index("#! tia: V20") < lines.index("#!end"),
       "tia after templates, inside the block")
    ok("tia" not in header.workspace_fields(run="r1", project="8XXX", plcs=["n1"]), "absent when not given")


def test_system_declares_the_option_matching_op5():
    eq(SYSTEM.project_options, (tia_version.OPTION,), "the safety system asks for the TIA version at New project")
    eq(tia_version.OPTION.key, "tia_version")
    source = open(_OPENNESS_SETUP, encoding="utf-8").read()
    low = int(re.search(r"MinimumPortalMajorVersion\s*=\s*(\d+)", source).group(1))
    high = int(re.search(r"MaximumPortalMajorVersion\s*=\s*(\d+)", source).group(1))
    eq(tia_version.SUPPORTED, tuple(f"V{v}" for v in range(low, high + 1)),
       "PL5 offers exactly the versions OP5 can attach to (OpennessSetup.cs)")


def test_project_options_and_default():
    options = project.project_options(["siemens_s7_safety"])
    eq([o.key for o in options], ["tia_version"])
    eq(project.project_options(["siemens_s7_safety", "siemens_s7_safety"]), options, "one per key")
    eq(project.project_options([]), [])
    eq(project.option_default(options[0]), "V20", "the dialog preselects the builtin value")


def test_create_project_writes_the_choice():
    def body(d):
        config.use_builtin()
        root = project.create_project(d, "Tia19", ["siemens_s7_safety"], False, 5, {"tia_version": "V19"})
        params = config.load_params(os.path.join(root, "config_project", "shared", "project_params.yaml"))
        eq(params.get("tia_version"), "V19", "the top-level key of the project's params")
        eq(tia_version.active(), "V19", "the opened project targets V19")
        eq(project.load_project_meta(root).get("name"), "Tia19", "the meta still written")
        text = open(os.path.join(root, "config_project", "shared", "project_params.yaml"), encoding="utf-8").read()
        ok("# the TIA Portal the SimaticML targets" in text, "the template's comment survives the round-trip")
        eq(text.count("tia_version:"), 1, "the key replaced in place, not duplicated")
        plain = project.create_project(d, "Plain", ["siemens_s7_safety"], False, 5)
        eq(tia_version.active(), "V20", "no option given -> the scaffolded builtin value")
        ok(os.path.isdir(plain))
        raises(ValueError, lambda: project.create_project(d, "Bad", ["siemens_s7_safety"], False, 5,
                                                          {"tia_version": "V21"}))
        ok(not os.path.exists(os.path.join(d, "Bad")), "an unoffered value is refused before anything is created")
        raises(ValueError, lambda: project.create_project(d, "Odd", ["siemens_s7_safety"], False, 5,
                                                          {"colour": "red"}))
        ok(not os.path.exists(os.path.join(d, "Odd")), "an unknown option is refused before anything is created")
    _with_temp_localappdata(body)


def test_new_project_dialog_offers_the_option():
    """The kernel dialog renders the selected type's option as a read-only dropdown preselected at the builtin
    value; a pick survives a type refresh and reaches create_project (a method of the dialog once shadowed
    tkinter's own `_options` and broke the window - building it is the test)."""
    import tkinter as tk
    from tkinter import ttk
    from pipeline5.workbench.new_project import NewProjectDialog
    root = tk.Tk()
    root.withdraw()
    try:
        dialog = NewProjectDialog(root, "en")
        boxes = [w for w in dialog._option_rows if isinstance(w, ttk.Combobox)]
        labels = [w.cget("text") for w in dialog._option_rows if isinstance(w, ttk.Label)]
        eq(labels, ["TIA Portal version"])
        eq([b.get() for b in boxes], ["V20"], "preselected at the builtin value")
        eq(tuple(boxes[0].cget("values")), tia_version.SUPPORTED)
        eq(str(boxes[0].cget("state")), "readonly")
        boxes[0].set("V18")
        dialog._enforce_selection()                       # a type change rebuilds the rows
        eq(dialog._chosen_options(), {"tia_version": "V18"}, "the pick survives the rebuild")
        dialog.destroy()
    finally:
        root.destroy()


if __name__ == "__main__":
    import sys
    sys.exit(run("tia_version", [
        ("new_project_dialog_offers_the_option", test_new_project_dialog_offers_the_option),
        ("normalize_spellings", test_normalize_spellings),
        ("blank_or_missing_means_the_builtin_value", test_blank_or_missing_means_the_builtin_value),
        ("stamp_and_line", test_stamp_and_line),
        ("workspace_header_carries_tia", test_workspace_header_carries_tia),
        ("system_declares_the_option_matching_op5", test_system_declares_the_option_matching_op5),
        ("project_options_and_default", test_project_options_and_default),
        ("create_project_writes_the_choice", test_create_project_writes_the_choice),
    ]))
