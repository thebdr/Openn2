"""The phase-bar icon registry (the Tk-free half of `gui/icons.py`): yaml -> mapping, path resolution,
and the fail-soft missing-file warning. The PhotoImage layer + on-screen look are a manual
`python launch_gui.py` check."""
import os

from _harness import run, eq, ok
from pipeline5.systems.plc_based.siemens_s7.safety.system import SYSTEM
from pipeline5.workbench import icons


def test_registry_covers_every_phase():
    reg = icons.load_registry()
    ok(reg, "registry loads non-empty")
    for phase in SYSTEM.phases:
        key = "run" if phase.number == 0 else str(phase.number)
        ok(key in reg, f"phase {key} has an icon row")


def test_every_registry_file_exists():
    found, warnings = icons.resolve(icons.load_registry())
    eq(warnings, [], "no missing icon files in the shipped registry")
    for key, path in found.items():
        ok(os.path.exists(path), f"{key} -> {os.path.basename(path)} exists")


def test_missing_file_warns_not_raises():
    found, warnings = icons.resolve({"100": "check-mark-button.png", "999": "no-such.png"})
    ok("100" in found and "999" not in found, "the good row resolves, the bad one drops")
    eq(len(warnings), 1, "one warning for the missing file")
    ok("no-such.png" in warnings[0], "the warning names the file")


def test_the_app_windows_get_the_pipeline5_icon():
    """User 2026-10-10 ("pl5 did not get the icon from assets"): the app sets assets/Pipeline5.png as the default
    icon of every window (`iconphoto(True, ...)` - title bar + taskbar, as PL3 did) and keeps the image; a missing
    file leaves Tk's icon, never an error."""
    import tkinter as tk
    from pipeline5.workbench import app_main
    ok(os.path.isfile(app_main.ICON) and app_main.ICON.endswith(os.path.join("assets", "Pipeline5.png")))
    root = tk.Tk()
    root.withdraw()
    calls = []
    try:
        root.iconphoto = lambda default, *images: calls.append((default, images))
        image = app_main.window_icon(root)
        eq((image.width(), image.height()), (144, 144), "the asset's image")
        eq(calls, [(True, (image,))], "the default for every window")
        original = app_main.ICON
        app_main.ICON = os.path.join(os.path.dirname(original), "no-such.png")
        try:
            eq(app_main.window_icon(root), None, "a missing file: Tk's own icon")
        finally:
            app_main.ICON = original
        eq(len(calls), 1, "nothing set for the missing file")
    finally:
        root.destroy()


def test_absent_registry_is_empty():
    eq(icons.load_registry(path=os.path.join(icons.ICONS_DIR, "no-such.yaml")), {},
       "an absent registry -> no icons, not an error")


if __name__ == "__main__":
    import sys
    sys.exit(run("gui_icons", [
        ("registry_covers_every_phase", test_registry_covers_every_phase),
        ("every_registry_file_exists", test_every_registry_file_exists),
        ("missing_file_warns_not_raises", test_missing_file_warns_not_raises),
        ("absent_registry_is_empty", test_absent_registry_is_empty),
        ("the_app_windows_get_the_pipeline5_icon", test_the_app_windows_get_the_pipeline5_icon),
    ]))
