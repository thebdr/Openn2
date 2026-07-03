"""The busy-strip pixel chase (gui/chasebar.py) - the PURE half: well-formed sprite pixel maps, the
jump arc, and the chase_step state machine (random lead drift + clamps, the border take-off, the
frozen-coyote jump, the landing direction flip). The canvas rendering is a scripted+manual check."""
from _harness import run, eq, ok
from pipeline4.gui import chasebar as cb


def test_sprites_well_formed():
    for name, frames, colors in (("roadrunner", cb.ROADRUNNER, cb._RR_COLORS),
                                 ("coyote", cb.COYOTE, cb._CY_COLORS)):
        widths = {len(row) for frame in frames for row in frame}
        eq(len(widths), 1, f"{name}: every row of every frame has the same width")
        eq(len({len(frame) for frame in frames}), 1, f"{name}: both frames have the same row count")
        chars = {ch for frame in frames for row in frame for ch in row}
        ok(chars <= set(colors) | {"."}, f"{name}: only declared colours + transparent ({chars})")
        ok(any(ch != "." for ch in chars), f"{name}: not empty")


def test_jump_arc():
    eq(cb.jump_arc(0.0), 0.0, "take-off at ground")
    eq(cb.jump_arc(1.0), 0.0, "landing at ground")
    eq(cb.jump_arc(0.5), 1.0, "apex at mid-flight")
    ok(cb.jump_arc(0.25) == cb.jump_arc(0.75), "symmetric arc")


def _state(**over):
    base = {"dir": 1, "cx": 200.0, "gap": 30.0, "rx": 0.0, "rw": 32.0, "cw": 36.0, "jump": None}
    base.update(over)
    return base


def test_chase_step_running():
    steady = lambda: 0.45                      # rand()*4 - 1.8 = 0 -> the lead holds steady
    s = cb.chase_step(_state(), 600.0, steady)
    eq(s["cx"], 200.0 + cb.SPEED, "the coyote advances at SPEED")
    eq(s["gap"], 30.0, "a steady rand holds the lead")
    eq(s["rx"], s["cx"] + (36.0 / 2 + 32.0 / 2) + 30.0, "the roadrunner rides ahead by spans + gap")
    ok(s["jump"] is None, "no border, no jump")
    grow = cb.chase_step(_state(), 600.0, lambda: 0.99)
    shrink = cb.chase_step(_state(), 600.0, lambda: 0.0)
    ok(grow["gap"] > 30.0 > shrink["gap"], "the lead drifts with the random draw")
    s = _state(gap=cb.GAP_MAX)
    eq(cb.chase_step(s, 600.0, lambda: 0.99)["gap"], cb.GAP_MAX, "the lead clamps at GAP_MAX")
    s = _state(gap=cb.GAP_MIN)
    eq(cb.chase_step(s, 600.0, lambda: 0.0)["gap"], cb.GAP_MIN, "the lead clamps at GAP_MIN")


def test_chase_step_border_jump_and_flip():
    steady = lambda: 0.45
    s = _state(cx=520.0)                        # near the right border of a 600px bar
    for _ in range(80):                         # run until the take-off triggers
        s = cb.chase_step(s, 600.0, steady)
        if s["jump"] is not None:
            break
    ok(s["jump"] is not None, "reaching the border takes off")
    hi = 600.0 - cb.MARGIN - 16.0               # the clamp ceiling for the bird centre (rw/2 = 16)
    ok(s["jump_from"] <= hi, "the take-off point clamps inside the bar")
    eq(s["jump_to"], s["cx"] - (36.0 / 2 + 32.0 / 2 + cb.LAND_GAP),
       "the landing is BEHIND the coyote (the bird arcs over it)")
    cx_frozen = s["cx"]
    ticks = 0
    while s["jump"] is not None:                # mid-air: the coyote skids, the arc progresses
        s = cb.chase_step(s, 600.0, steady)
        ticks += 1
        eq(s["cx"], cx_frozen, "the coyote is frozen during the jump")
        ok(ticks <= cb.JUMP_TICKS + 2, "the jump terminates")
    eq(s["dir"], -1, "landing reverses the chase")
    eq(s["gap"], cb.LAND_GAP, "the lead resets on landing")
    eq(s["rx"], s["jump_to"], "the bird lands at the arc's endpoint")
    s2 = cb.chase_step(s, 600.0, steady)
    eq(s2["rx"], s2["cx"] - (36.0 / 2 + 32.0 / 2) - s2["gap"],
       "the chase resumes leftwards with the bird ahead")


def test_chase_step_left_border():
    steady = lambda: 0.45
    s = _state(dir=-1, cx=80.0)
    for _ in range(80):
        s = cb.chase_step(s, 600.0, steady)
        if s["jump"] is not None:
            break
    ok(s["jump"] is not None, "the LEFT border also takes off")
    ok(s["jump_to"] > s["cx"], "the landing is to the RIGHT of the coyote (behind it, heading left)")
    while s["jump"] is not None:
        s = cb.chase_step(s, 600.0, steady)
    eq(s["dir"], 1, "the chase reverses to rightwards")


if __name__ == "__main__":
    import sys
    sys.exit(run("gui_chasebar", [
        ("sprites_well_formed", test_sprites_well_formed),
        ("jump_arc", test_jump_arc),
        ("chase_step_running", test_chase_step_running),
        ("chase_step_border_jump_and_flip", test_chase_step_border_jump_and_flip),
        ("chase_step_left_border", test_chase_step_left_border),
    ]))
