"""The phase-bar icon registry (the Tk-free half of `gui/icons.py`): yaml -> mapping, path resolution,
and the fail-soft missing-file warning. The PhotoImage layer + on-screen look are a manual
`python launch_gui.py` check."""
import os

from _harness import run, eq, ok
from pipeline5.workbench import icons
from pipeline5.workbench import phase_model as phases


def test_registry_covers_every_phase():
    reg = icons.load_registry()
    ok(reg, "registry loads non-empty")
    for phase in phases.PHASES:
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
    ]))
