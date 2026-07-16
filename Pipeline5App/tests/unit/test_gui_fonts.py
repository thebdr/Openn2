"""gui/fonts.py + theme font wiring - the bundled Monaspace asset is found at the right path and the
app-wide size is 13. (register()/family() need Tk + Windows, so they are exercised by the manual
`launch_gui.py` check + the construction smoke, not the headless gate.)"""
import os

from _harness import run, eq, ok
from pipeline5.workbench import fonts
from pipeline5.workbench import theme


def test_font_path_points_at_bundled_asset():
    tail = os.path.join("assets", "fonts", "MonaspaceNeon-Var.ttf")
    ok(fonts.FONT_PATH.endswith(tail), f"FONT_PATH ends with {tail}: {fonts.FONT_PATH}")
    ok(os.path.exists(fonts.FONT_PATH), "the bundled Monaspace Neon Var TTF is present in the repo")
    eq(fonts.FAMILY, "Monaspace Neon Var", "the Tk family the registered face resolves to")
    eq(fonts.FALLBACK, "Consolas", "the graceful fallback when the bundled font can't register")


def test_app_font_contract():
    # the size is user-tunable; assert the CONTRACT (a positive int + MONO_FONT tracks it), not a value.
    ok(isinstance(theme.APP_FONT_SIZE, int) and theme.APP_FONT_SIZE > 0, "APP_FONT_SIZE is a positive int")
    eq(theme.MONO_FONT[1], theme.APP_FONT_SIZE, "MONO_FONT default size tracks APP_FONT_SIZE")


if __name__ == "__main__":
    import sys
    sys.exit(run("gui_fonts", [
        ("font_path_points_at_bundled_asset", test_font_path_points_at_bundled_asset),
        ("app_font_contract", test_app_font_contract),
    ]))
