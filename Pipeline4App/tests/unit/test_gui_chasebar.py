"""The busy-strip pixel chase (gui/chasebar.py) - the PURE half: well-formed sprite pixel maps, the
jump arc, and the chase_step state machine (random lead drift + clamps, the border take-off, the
frozen-coyote jump, the landing direction flip). The canvas rendering is a scripted+manual check."""
from _harness import run, eq, ok
from pipeline4.gui import chasebar as cb


def test_sprites_well_formed():
    for name, frames, colors in (("roadrunner", cb.ROADRUNNER, cb._RR_COLORS),
                                 ("coyote", cb.COYOTE, cb._CY_COLORS),
                                 ("mario", cb.MARIO, cb._MARIO_COLORS),
                                 ("morty", cb.MORTY, cb._MORTY_COLORS),
                                 ("mickey", cb.MICKEY, cb._MICKEY_COLORS),
                                 ("rocket", cb.ROCKET, cb._ROCKET_COLORS)):
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
    base = {"dir": 1, "cx": 200.0, "gap": 30.0, "gap_t": 30.0, "rx": 0.0,
            "rw": 32.0, "cw": 36.0, "fw": [24.0, 24.0, 24.0, 32.0], "followers": [], "jump": None}
    base.update(over)
    return base


def test_chase_step_running():
    steady = lambda: 0.45
    s = cb.chase_step(_state(gap=30.0, gap_t=80.0), 2000.0, steady)
    eq(s["cx"], 200.0 + cb.SPEED, "the coyote advances at SPEED (the 10x pace)")
    eq(s["gap"], 30.0 + cb.GAP_RATE, "the lead moves toward its target at GAP_RATE")
    eq(s["rx"], s["cx"] + (36.0 / 2 + 32.0 / 2) + s["gap"], "the bird rides ahead by spans + gap")
    ok(s["jump"] is None, "no border, no jump")
    s = cb.chase_step(_state(gap=80.0, gap_t=20.0), 2000.0, steady)
    eq(s["gap"], 80.0 - cb.GAP_RATE, "a lower target squeezes the lead")
    # reaching the target picks a NEW random target (the lead visibly wanders, never sits still)
    s = cb.chase_step(_state(gap=30.0, gap_t=30.0), 2000.0, lambda: 0.5)
    eq(s["gap_t"], cb.GAP_MIN + 0.5 * (cb.GAP_MAX - cb.GAP_MIN), "arrival retargets the lead")
    # the floor: gap 0 = the coyote's head TOUCHES the bird's tail - never less (no collision)
    s = _state(gap=3.0, gap_t=0.0)
    for _ in range(40):
        s = cb.chase_step(s, 20000.0, lambda: 0.0)     # rand 0 -> retargets always pick GAP_MIN
        ok(s["gap"] >= 0.0, "the lead never goes below touching")
    eq(s["gap"], 0.0, "the lead can REACH exactly touching (head = tail)")
    eq(s["rx"] - 16.0, s["cx"] + 18.0, "at gap 0 the sprite edges meet exactly")


def test_chase_step_follower_train():
    steady = lambda: 0.45
    s = _state(followers=[{"x": 500.0, "gap": 20.0}])
    s1 = cb.chase_step(s, 2000.0, steady)
    f = s1["followers"][0]
    target = s1["cx"] - (36.0 / 2 + 24.0 / 2 + f["gap"])
    ok(abs(f["x"] - 500.0) <= cb.FOLLOWER_SPEED, "a follower moves at most FOLLOWER_SPEED per tick")
    ok(abs(f["x"] - target) <= abs(500.0 - target), "…toward its behind-the-coyote target")
    eq(s["followers"][0]["x"], 500.0, "chase_step never mutates the caller's follower dicts")
    for _ in range(200):
        s1 = cb.chase_step(s1, 20000.0, steady)
        ok(cb.FOLLOWER_GAP_LO <= s1["followers"][0]["gap"] <= cb.FOLLOWER_GAP_HI,
           "a follower's distance stays clamped")
        if s1["jump"] is not None:
            break
    f = s1["followers"][0]
    settled = s1["cx"] - (36.0 / 2 + 24.0 / 2 + f["gap"])
    ok(abs(f["x"] - settled) < cb.FOLLOWER_SPEED + 1, "the follower settles onto its wander distance")
    # a SECOND follower chains behind the FIRST, not behind the coyote
    s2 = _state(followers=[{"x": 150.0, "gap": 10.0}, {"x": 100.0, "gap": 10.0}])
    s3 = cb.chase_step(s2, 20000.0, steady)
    f0, f1 = s3["followers"]
    chained = f0["x"] - (24.0 / 2 + 24.0 / 2 + f1["gap"])
    ok(abs(f1["x"] - chained) <= abs(100.0 - chained), "follower 2 targets follower 1's back")


def test_chase_step_train_joins_per_border():
    """Each landing adds ONE follower (Mario, Morty, Mickey, the rocket), then no more."""
    steady = lambda: 0.45
    s = _state(cx=300.0)
    landings = 0
    for _ in range(3000):
        was_jumping = s["jump"] is not None
        s = cb.chase_step(s, 600.0, steady)
        if was_jumping and s["jump"] is None:
            landings += 1
            eq(len(s["followers"]), min(landings, 4),
               f"landing {landings} -> {min(landings, 4)} followers in the train")
            if landings == 4:
                border = 600.0 - cb.MARGIN - 16.0 if s["dir"] < 0 else cb.MARGIN + 16.0
                eq(s["followers"][3]["x"], border, "the rocket (fw 32) spawns AT the border")
        if landings >= 6:
            break
    ok(landings >= 6, "the chase kept cycling")
    eq(len(s["followers"]), 4, "landings past the 4th add NO more followers")


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
    eq(len(s["followers"]), 1, "the FIRST border event spawns exactly one follower (Mario)")
    eq(s["followers"][0]["x"], 600.0 - cb.MARGIN - 12.0,
       "…AT the border the bird just left (behind the coyote)")
    entrance = s["followers"][0]["x"]
    s2 = cb.chase_step(s, 600.0, steady)
    eq(s2["rx"], s2["cx"] - (36.0 / 2 + 32.0 / 2) - s2["gap"],
       "the chase resumes leftwards with the bird ahead")
    ok(s2["followers"][0]["x"] < entrance, "Mario runs in after the coyote")


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
        ("chase_step_follower_train", test_chase_step_follower_train),
        ("chase_step_train_joins_per_border", test_chase_step_train_joins_per_border),
        ("chase_step_border_jump_and_flip", test_chase_step_border_jump_and_flip),
        ("chase_step_left_border", test_chase_step_left_border),
    ]))
