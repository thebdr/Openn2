"""The cosmetic app_config (`user_interface`) loaders - the log-viewer font size. Pure; the live values
in app_config.yaml are user-owned, so we assert the CONTRACT (a valid choice), never a fixed number."""
from _harness import run, eq, ok
from pipeline4.core import config


def test_resolve_font_size():
    eq(config._resolve_font_size("12"), 12, "a stored string coerces")
    eq(config._resolve_font_size(14), 14)
    eq(config._resolve_font_size(99), 10, "out-of-range -> default 10")
    eq(config._resolve_font_size("x"), 10, "non-int -> default 10")
    eq(config._resolve_font_size(None), 10, "absent -> default 10")
    ok(all(s in config.APP_FONT_SIZES for s in (10, 12, 14)), "the 3 dropdown choices")


def test_load_app_ui_exposes_font_size():
    ui = config.load_app_ui()
    ok("font_size" in ui, "load_app_ui exposes font_size")
    ok(ui["font_size"] in config.APP_FONT_SIZES, "the loaded font_size is one of the valid choices")
    ok("language" in ui and "log_levels" in ui, "the other user_interface keys still load")


if __name__ == "__main__":
    import sys
    sys.exit(run("app_config", [
        ("resolve_font_size", test_resolve_font_size),
        ("load_app_ui_exposes_font_size", test_load_app_ui_exposes_font_size),
    ]))
