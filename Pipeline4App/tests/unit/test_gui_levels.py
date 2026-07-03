"""GUI M1 - the Levels dropdown persistence: config.save_app_log_levels round-trips the BUILTIN
app_config.yaml (FAIL/ERRR always included, comments preserved) and load_app_ui reads it back.
UI prefs are APP-scoped - saving with a project OPEN must land in the same (builtin) file the next
launch reads, never in the project's copy (the production-test persistence bug). Hermetic: the
builtin app_config home is redirected to a temp file."""
import os
import tempfile

from _harness import run, eq, ok
from pipeline4.core import config


def _with_temp_builtin_ui(fn):
    """Run fn(dir) with config.builtin_app_config_file (the app-scoped UI-pref home, used by BOTH
    the loaders and the savers) redirected into a temp dir - the tracked builtin stays untouched."""
    orig = config.builtin_app_config_file
    with tempfile.TemporaryDirectory() as d:
        config.builtin_app_config_file = lambda: os.path.join(d, "app_config.yaml")
        try:
            fn(d)
        finally:
            config.builtin_app_config_file = orig


def test_save_and_load_log_levels():
    def body(d):
        with open(os.path.join(d, "app_config.yaml"), "w", encoding="utf-8") as h:
            h.write("# keep me\nuser_interface:\n  log_levels: [F, E, W, I, S, P, D]\n")
        # the user unchecks everything toggleable, leaving only WARN (+ the forced UNHIDEABLE set)
        config.save_app_log_levels({"WARN"})
        shown = config.load_app_ui()["log_levels"]
        ok({"FAIL", "ERRR", "INFO", "RSLT", "WARN"} <= shown,
           "FAIL+ERRR+INFO+RSLT forced (greyed in the dropdown), WARN kept")
        ok("PASS" not in shown and "SKIP" not in shown, "the unchecked toggleable levels dropped")
        text = open(os.path.join(d, "app_config.yaml"), encoding="utf-8").read()
        ok("# keep me" in text, "the file comment survived the round-trip")
        ok("log_levels" in text and "[" in text, "log_levels written in flow form")
    _with_temp_builtin_ui(body)


def test_save_creates_file_when_absent():
    def body(_d):
        config.save_app_log_levels({"WARN", "INFO", "PASS", "SKIP", "DEBG"})
        shown = config.load_app_ui()["log_levels"]
        eq(shown - {"PHASE"}, {"FAIL", "ERRR", "WARN", "INFO", "PASS", "SKIP", "RSLT", "DEBG"},
           "all levels (the forced set + the rest) written + read back")
    _with_temp_builtin_ui(body)


def test_ui_prefs_are_app_scoped_not_project_scoped():
    """The persistence regression: toggling language/levels while a PROJECT is open must write the
    BUILTIN (app) file - the one the next launch reads BEFORE auto_reopen - and must leave the
    project's own app_config.yaml untouched."""
    def body(_d):
        with tempfile.TemporaryDirectory() as proj:
            cfgdir = os.path.join(proj, "config_project")
            os.makedirs(cfgdir)
            project_copy = os.path.join(cfgdir, "app_config.yaml")
            with open(project_copy, "w", encoding="utf-8") as h:
                h.write("user_interface:\n  language: en\n  log_levels: [F, E, W, I, S, P, D]\n")
            config.use_project(proj)
            try:
                config.save_app_language("it")
                config.save_app_log_levels({"WARN"})
            finally:
                config.use_builtin()
            ui = config.load_app_ui()                     # what the NEXT LAUNCH reads (pre-auto_reopen)
            eq(ui["language"], "it", "the language toggle survives a restart")
            eq(ui["log_levels"] - {"PHASE"}, {"FAIL", "ERRR", "INFO", "RSLT", "WARN"},
               "the levels toggle survives a restart (+ the forced set)")
            with open(project_copy, encoding="utf-8") as h:
                text = h.read()
            ok("language: en" in text and "[F, E, W, I, S, P, D]" in text,
               "the project's own app_config.yaml is NOT touched by UI-pref saves")
    _with_temp_builtin_ui(body)


if __name__ == "__main__":
    import sys
    sys.exit(run("gui_levels", [
        ("save_and_load_log_levels", test_save_and_load_log_levels),
        ("save_creates_file_when_absent", test_save_creates_file_when_absent),
        ("ui_prefs_are_app_scoped_not_project_scoped", test_ui_prefs_are_app_scoped_not_project_scoped),
    ]))
