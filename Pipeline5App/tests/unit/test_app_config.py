"""The cosmetic app_config (`user_interface`) loaders/savers - font size, theme, window size, log-to-file.
The pure resolvers + the load CONTRACT are asserted against the live file (user-owned values, so never a
fixed number); the savers are round-tripped against a REDIRECTED temp file so the tracked builtin is untouched."""
import os
import tempfile

from _harness import run, eq, ok
from pipeline5.core import config


def _with_temp_app_config(fn):
    """Run fn() with the UI-pref home (config.builtin_app_config_file - the loaders AND savers are
    pinned to the BUILTIN file, app-scoped) redirected to a fresh temp file, so the tracked builtin
    is untouched."""
    orig = config.builtin_app_config_file
    with tempfile.TemporaryDirectory() as d:
        config.builtin_app_config_file = lambda: os.path.join(d, "app_config.yaml")
        try:
            fn()
        finally:
            config.builtin_app_config_file = orig


def test_resolve_font_size():
    eq(config._resolve_font_size("12"), 12, "a stored string coerces")
    eq(config._resolve_font_size(14), 14)
    eq(config._resolve_font_size(99), 10, "out-of-range -> default 10")
    eq(config._resolve_font_size("x"), 10, "non-int -> default 10")
    eq(config._resolve_font_size(None), 10, "absent -> default 10")
    ok(all(s in config.APP_FONT_SIZES for s in (10, 12, 14)), "the 3 dropdown choices")


def test_resolve_theme_and_dim():
    eq(config._resolve_theme("light"), "light", "light stays light")
    eq(config._resolve_theme("LIGHT"), "light", "case-insensitive")
    eq(config._resolve_theme("dark"), "dark")
    eq(config._resolve_theme(None), "dark", "absent -> dark")
    eq(config._resolve_theme("nope"), "dark", "unknown -> dark")
    eq(config._resolve_dim("1400", 720), 1400, "a stored string coerces")
    eq(config._resolve_dim(100, 720), 720, "too small (<400) -> default")
    eq(config._resolve_dim("x", 720), 720, "non-int -> default")
    eq(config._resolve_dim(None, 720), 720, "absent -> default")


def test_load_app_ui_exposes_keys():
    ui = config.load_app_ui()
    ok(ui["font_size"] in config.APP_FONT_SIZES, "font_size is a valid choice")
    ok("language" in ui and "log_levels" in ui, "the original keys still load")
    ok(ui["theme"] in ("light", "dark"), "theme is light|dark")
    ok(isinstance(ui["width"], int) and ui["width"] >= 400, "width is a sane int")
    ok(isinstance(ui["height"], int) and ui["height"] >= 400, "height is a sane int")
    ok(isinstance(ui["log_to_file"], bool), "log_to_file is a bool")


def test_m7_savers_roundtrip():
    def body():
        config.save_app_theme("light")
        config.save_app_window_size(1400, 900)
        config.save_app_log_to_file(True)
        ui = config.load_app_ui()
        eq(ui["theme"], "light", "theme persisted")
        eq(ui["width"], 1400, "width persisted")
        eq(ui["height"], 900, "height persisted")
        eq(ui["log_to_file"], True, "log_to_file persisted")
        config.save_app_theme("bogus")                  # normalized on the way in
        eq(config.load_app_ui()["theme"], "dark", "an unknown theme normalizes to dark")
        config.save_app_log_to_file(False)
        eq(config.load_app_ui()["log_to_file"], False, "log_to_file toggles back off")
        # the simple savers share _save_app_ui and don't clobber each other's keys
        config.save_app_language("it")
        ui = config.load_app_ui()
        eq(ui["language"], "it", "language coexists")
        eq(ui["width"], 1400, "width survives a later language save")
    _with_temp_app_config(body)


def test_gui_log_dir_under_reports():
    ok(config.gui_log_dir().replace("\\", "/").endswith("ProjectDocumentation/Reports/Logs"),
       "the GUI log tee writes under the reports tree")


if __name__ == "__main__":
    import sys
    sys.exit(run("app_config", [
        ("resolve_font_size", test_resolve_font_size),
        ("resolve_theme_and_dim", test_resolve_theme_and_dim),
        ("load_app_ui_exposes_keys", test_load_app_ui_exposes_keys),
        ("m7_savers_roundtrip", test_m7_savers_roundtrip),
        ("gui_log_dir_under_reports", test_gui_log_dir_under_reports),
    ]))
