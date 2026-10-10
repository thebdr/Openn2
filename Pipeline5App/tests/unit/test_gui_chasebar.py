"""The busy-strip pixel chase (gui/chasebar.py) - the PURE half: well-formed sprite pixel maps, the
jump arc, and the chase_step state machine (random lead drift + clamps, the border take-off, the
frozen-coyote jump, the landing direction flip). The canvas rendering is a scripted+manual check."""
from _harness import run, eq, ok
from pipeline5.workbench import chasebar as cb


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


def test_chase_step_is_time_based():
    """User 2026-10-10 ("the animation during the running phases lags, can it be smooth?"): a step of k reference
    ticks moves k times as far - two half steps land where one full step does, a late frame (k=3) keeps the speed -
    the jump progresses by k / JUMP_TICKS, and the early-retarget chance scales as 1 - (1 - p)**k (k=1: exactly p)."""
    steady = lambda: 0.45
    full = cb.chase_step(_state(gap=30.0, gap_t=80.0), 2000.0, steady, 1.0)
    half = cb.chase_step(cb.chase_step(_state(gap=30.0, gap_t=80.0), 2000.0, steady, 0.5), 2000.0, steady, 0.5)
    eq((half["cx"], half["gap"]), (full["cx"], full["gap"]), "two half steps = one full step")
    eq(cb.chase_step(_state(), 2000.0, steady, 3.0)["cx"], 200.0 + 3 * cb.SPEED, "a late frame keeps the speed")
    eq(cb.chase_step(_state(jump=0.0, jump_from=0.0, jump_to=0.0), 2000.0, steady, 0.5)["jump"],
       0.5 / cb.JUMP_TICKS, "the jump advances by k / JUMP_TICKS")
    draws = []
    rand = lambda: draws.append(None) or 0.019           # just under RETARGET_P (0.02): retargets at k=1 ...
    cb.chase_step(_state(gap=30.0, gap_t=80.0), 2000.0, rand, 1.0)
    eq(len(draws), 2, "... (the chance, then the new target)")
    draws.clear()
    cb.chase_step(_state(gap=30.0, gap_t=80.0), 2000.0, rand, 0.5)
    eq(len(draws), 1, "... but not on a half step (chance 1 - 0.98**0.5 < 0.019)")
    eq(cb.chase_step(_state(), 2000.0, steady)["cx"], 200.0 + cb.SPEED, "the default is one reference tick")


def test_the_bar_frames_run_on_the_clock():
    """The canvas: a frame every FRAME_MS (~60 fps) moving by the REAL time since the last frame - a frame the busy
    UI thread delivers late moves further, not slower; a stall catches up at most MAX_STEP_S (no teleport)."""
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()
    try:
        bar = cb.ChaseBar(root)
        bar.start(12)
        eq(bar._interval, cb.FRAME_MS, "the app's 12 ms request runs at FRAME_MS")
        clock = iter([10.0, 10.0, 10.05, 10.05, 15.05, 15.05])   # each frame reads the clock twice (dt, its own cost)
        original = cb.time.perf_counter
        cb.time.perf_counter = lambda: next(clock)
        try:
            bar.after_cancel(bar._job)
            bar.winfo_width = lambda: 4000                  # a withdrawn canvas reports 1 px - room to run
            bar._state.update(cx=300.0, dir=1, gap=30.0, gap_t=30.0, jump=None)
            bar._tick()                                     # the first frame: no elapsed time yet
            x0 = bar._state["cx"]
            bar._tick()                                     # 50 ms later: two reference ticks
            x1 = bar._state["cx"]
            bar._tick()                                     # after a 5 s stall: capped at MAX_STEP_S
            x2 = bar._state["cx"]
        finally:
            cb.time.perf_counter = original
        eq((x0, round(x1 - x0, 6)), (300.0, round(2 * cb.SPEED, 6)), "50 ms = 2 reference ticks of travel")
        ok(abs(x2 - x1) <= cb.SPEED * cb.MAX_STEP_S / cb.TICK_S + 1e-6, f"a stall never teleports ({x2 - x1})")
        bar.stop()
    finally:
        root.destroy()


def test_busy_switch_hands_the_gil_over_while_a_phase_runs():
    """The App gives the UI thread the GIL in time for every frame while a phase runs (BUSY_SWITCH_S) and puts the
    interval back when idle; a second busy call keeps the ORIGINAL to restore."""
    import sys
    from pipeline5.workbench import app_main
    before = sys.getswitchinterval()
    try:
        app_main.busy_switch(True)
        eq(sys.getswitchinterval(), app_main.BUSY_SWITCH_S)
        app_main.busy_switch(True)
        app_main.busy_switch(False)
        eq(sys.getswitchinterval(), before, "restored to the interval before the run")
        app_main.busy_switch(False)
        eq(sys.getswitchinterval(), before, "an idle call changes nothing")
    finally:
        sys.setswitchinterval(before)


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
        ("chase_step_is_time_based", test_chase_step_is_time_based),
        ("the_bar_frames_run_on_the_clock", test_the_bar_frames_run_on_the_clock),
        ("busy_switch_hands_the_gil_over_while_a_phase_runs", test_busy_switch_hands_the_gil_over_while_a_phase_runs),
    ]))
