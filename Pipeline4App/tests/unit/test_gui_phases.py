"""GUI M0 - the phase registry (gui/phases.py): the single source of the phase order the bar + Run-all
consume. Pure + data-independent (the GUI itself is a manual `python launch_gui.py` check)."""
from _harness import run, eq, ok
from pipeline4.gui import phases


def test_registry_shape():
    nums = [p.number for p in phases.PHASES]
    eq(nums[0], 0, "Run-all (0) is first")
    ok(200 not in nums, "PL4 has no Fill phase (200)")
    eq([n for n in nums if n], [100, 300, 400, 500, 600, 700, 800, 900], "the 8 PL4 phases, ascending")


def test_runnable():
    runnable = [p.number for p in phases.RUNNABLE]
    ok(0 not in runnable, "Run-all is not a runnable phase")
    ok(all(phases.by_number(n).handler for n in runnable), "every RUNNABLE phase names a handler")
    eq(set(runnable), {100, 300, 400, 500, 600, 700, 800, 900})


def test_run_order():
    order = phases.run_order()
    eq(order[0], 300, "staging runs first")
    eq(order[-2:], [900, 100], "reporting + validation run last")
    eq(set(order), {100, 300, 400, 500, 600, 700, 800, 900}, "every runnable phase")
    eq(len(order), len(set(order)), "no duplicates")


def test_by_number():
    eq(phases.by_number(800).handler, "_run_software")
    eq(phases.by_number(900).handler, "_run_reporting")
    eq(len(phases.by_number(100).subs), 4, "phase 100 carries its 4 sub-phases")
    eq(phases.by_number(999), None, "an unknown number -> None")


if __name__ == "__main__":
    import sys
    sys.exit(run("gui_phases", [
        ("registry_shape", test_registry_shape),
        ("runnable", test_runnable),
        ("run_order", test_run_order),
        ("by_number", test_by_number),
    ]))
