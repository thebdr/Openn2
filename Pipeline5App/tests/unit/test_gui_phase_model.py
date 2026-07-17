"""The Siemens phase registry (SYSTEM.phases, authored in safety/main.py): the phase order + the
sub-button set transcribed from the operator oracle ButtonsLayout.xlsx, now a per-system PhaseSet
dispatched through SYSTEM.handlers (step 5). Pure + data-independent (the GUI itself is a manual
`python launch_gui.py` check)."""
from _harness import run, eq, ok, raises
from pipeline5.language import i18n
from pipeline5.systems.plc_based.siemens_s7.safety.system import SYSTEM
from pipeline5.systems.system_contract import Phase, PhaseSet, Sub

phases = SYSTEM.phases


def test_registry_shape():
    nums = [p.number for p in phases]
    eq(nums[0], 0, "Run-all (0) is first")
    ok(200 in nums, "phase 200 (Fill) is present")
    eq([n for n in nums if n], [100, 200, 300, 400, 500, 600, 700, 800, 900], "the 9 PL4 phases, ascending")


def test_runnable():
    runnable = [p.number for p in phases.runnable()]
    ok(0 not in runnable, "Run-all is not a runnable phase")
    eq(set(runnable), {100, 200, 300, 400, 500, 600, 700, 800, 900})


def test_every_handler_key_resolves():
    """The dispatch contract: every Phase.handler + every wired special's opens key must name a
    callable in SYSTEM.handlers - a typo'd key would grey a button or crash a click."""
    for p in phases.runnable():
        ok(callable(SYSTEM.handlers.get(p.handler)), f"phase {p.number} handler {p.handler!r} resolves")
    for p in phases:
        for s in p.subs:
            if s.kind == "special" and s.enabled and s.opens:
                ok(callable(SYSTEM.handlers.get(s.opens)), f"special {s.number} key {s.opens!r} resolves")


def test_run_order():
    order = phases.run_order()
    eq(order, [300, 400, 500, 600, 700, 800, 900, 100],
       "the explicit run_plan: staging first, builders ascending, reporting + validation last")
    ok(200 not in order, "ph200 fill is excluded from Run-all (it mutates the source doc)")
    order.append(999)
    eq(phases.run_order()[-1], 100, "run_order returns a fresh list (caller mutation is contained)")


def test_phase_set_validates_at_construction():
    """A registry typo must fail at SYSTEM import, not at the button click."""
    raises(ValueError, lambda: PhaseSet(phases=(Phase(100, "a"), Phase(100, "b"))))
    raises(ValueError, lambda: PhaseSet(phases=(Phase(100, "a", subs=(Sub(110, "x"), Sub(110, "y"))),)))
    raises(ValueError, lambda: PhaseSet(phases=(Phase(100, "a", handler="h"),), run_plan=(100, 300)))
    raises(ValueError, lambda: PhaseSet(phases=(Phase(100, "a"),), run_plan=(100,)))   # display-only phase
    raises(ValueError, lambda: PhaseSet(phases=(Phase(100, "a", handler="h"),), run_plan=(100, 100)))


def test_subs_match_oracle():
    # The exact sub-button numbers per phase (ButtonsLayout.xlsx).
    expected = {
        100: [110, 120, 130, 140, 150, 155, 156, 160, 170, 180, 190],  # 150 = the diagnosis checks (live)
        200: [210, 220, 230, 240, 245, 250],     # 245 = the PL4 "Risky Index Fill" orange button (not in the oracle)
        300: [310, 320, 330],
        400: [410, 420, 430],
        500: [510, 520, 530, 540],
        600: [610, 620, 630, 640],
        700: [710, 720, 730],
        800: [810, 820, 830, 840, 850],
        900: [910, 920, 940, 930],   # 940 = the PL4 before/after report (moved from 145 - it is a REPORT)
    }
    for num, subs in expected.items():
        eq([s.number for s in phases.by_number(num).subs], subs, f"phase {num} sub numbers")


def test_kinds_and_enablement():
    # open buttons carry an `opens` key; the deferred/unported ones are greyed (enabled=False).
    opens = {s.number for p in phases for s in p.subs if s.kind == "open"}
    eq(opens, {160, 170, 180, 190, 250, 330, 420, 530, 540, 630, 640, 730, 840, 850, 930}, "the open buttons")
    disabled = {s.number for p in phases for s in p.subs if not s.enabled}
    eq(disabled, {155, 156, 430, 810, 840, 920},
       "the deferred/unported (greyed) buttons")
    specials = {s.number for p in phases for s in p.subs if s.kind == "special"}
    eq(specials, {155, 156, 245, 430}, "the special buttons (Clean / custom-interface + the 245 Risky Index Fill)")
    eq(phases.sub_by_number(245).opens, "risky_index", "the wired special names its handlers key in opens")
    for n in (155, 156, 430):
        eq(phases.sub_by_number(n).opens, "", "an unwired special carries no handler key")
    for n in (160, 330, 530, 930):                       # a sampling of wired opens
        ok(phases.sub_by_number(n).opens, f"open button {n} names a target")
    # oracle titles that are easy to mis-transcribe (label_key -> EN via i18n, vs ButtonsLayout.xlsx)
    eq(phases.sub_by_number(320).label_key, "pb_stage_cematrix", "320 carries the C&E-matrix key")
    eq(i18n.tr(phases.sub_by_number(320).label_key), "Stage C&E Matrix", "320 EN = the oracle's Stage C&E Matrix")
    eq(i18n.tr(phases.sub_by_number(330).label_key), "Open IO Database", "330 EN = Open IO Database")


def test_labels_resolve_in_both_languages():
    # every phase name_key + every sub label_key must resolve to a NON-key string in EN and IT
    # (i.e. it exists in the i18n table - tr falls back to the key on a miss).
    keys = [p.name_key for p in phases]
    keys += [s.label_key for p in phases for s in p.subs]
    for key in keys:
        for lang in ("en", "it"):
            text = i18n.tr(key, lang)
            ok(text and text != key, f"{key} resolves in {lang} (got {text!r})")
    eq(i18n.tr("ph_staging", "it"), "Staging Documenti", "an IT header resolves")


def test_phase_of_sub():
    eq(phases.phase_of_sub(620).number, 600, "620 belongs to phase 600")
    eq(phases.phase_of_sub(110).number, 100, "110 belongs to phase 100")
    eq(phases.phase_of_sub(850).number, 800, "850 belongs to phase 800")
    eq(phases.phase_of_sub(999), None, "an unknown sub -> None")
    eq(i18n.tr(phases.sub_by_number(510).label_key), "Generate I/O Tags")


def test_by_number():
    eq(phases.by_number(800).handler, "software")
    eq(phases.by_number(900).handler, "reporting")
    eq(len(phases.by_number(100).subs), 11, "phase 100: the 11 oracle sub-buttons (the report moved to 900/940)")
    eq(phases.by_number(999), None, "an unknown number -> None")


if __name__ == "__main__":
    import sys
    sys.exit(run("gui_phases", [
        ("registry_shape", test_registry_shape),
        ("runnable", test_runnable),
        ("every_handler_key_resolves", test_every_handler_key_resolves),
        ("run_order", test_run_order),
        ("phase_set_validates_at_construction", test_phase_set_validates_at_construction),
        ("subs_match_oracle", test_subs_match_oracle),
        ("kinds_and_enablement", test_kinds_and_enablement),
        ("labels_resolve_in_both_languages", test_labels_resolve_in_both_languages),
        ("phase_of_sub", test_phase_of_sub),
        ("by_number", test_by_number),
    ]))
