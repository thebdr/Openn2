"""GUI M1 - the Levels dropdown persistence: config.save_app_log_levels round-trips app_config.yaml
(FAIL/ERROR always included, comments preserved) and load_app_ui reads it back. Hermetic (temp project)."""
import os
import tempfile

from _harness import run, eq, ok
from pipeline4.core import config


def test_save_and_load_log_levels():
    with tempfile.TemporaryDirectory() as d:
        config.use_project(d)
        try:
            cfgdir = os.path.join(d, "config_project")
            os.makedirs(cfgdir, exist_ok=True)
            with open(os.path.join(cfgdir, "app_config.yaml"), "w", encoding="utf-8") as h:
                h.write("# keep me\nuser_interface:\n  log_levels: [F, E, W, I, S, P, D]\n")
            # the user unchecks everything toggleable, leaving only WARN (+ the forced FAIL/ERROR)
            config.save_app_log_levels({"WARN"})
            shown = config.load_app_ui()["log_levels"]
            ok({"FAIL", "ERROR", "WARN"} <= shown, "FAIL+ERROR forced, WARN kept")
            ok("PASS" not in shown and "SKIP" not in shown and "INFO" not in shown, "the unchecked levels dropped")
            text = open(os.path.join(cfgdir, "app_config.yaml"), encoding="utf-8").read()
            ok("# keep me" in text, "the file comment survived the round-trip")
            ok("log_levels" in text and "[" in text, "log_levels written in flow form")
        finally:
            config.use_builtin()


def test_save_creates_file_when_absent():
    with tempfile.TemporaryDirectory() as d:
        config.use_project(d)
        try:
            config.save_app_log_levels({"WARN", "INFO", "PASS", "SKIP", "DEBUG"})
            shown = config.load_app_ui()["log_levels"]
            eq(shown - {"PHASE"}, {"FAIL", "ERROR", "WARN", "INFO", "PASS", "SKIP", "DEBUG"},
               "all levels (forced FAIL/ERROR + the rest) written + read back")
        finally:
            config.use_builtin()


if __name__ == "__main__":
    import sys
    sys.exit(run("gui_levels", [
        ("save_and_load_log_levels", test_save_and_load_log_levels),
        ("save_creates_file_when_absent", test_save_creates_file_when_absent),
    ]))
