"""The busy/progress strip as a PIXEL CHASE: a coyote chasing a roadrunner back and forth across
the bar. The roadrunner's lead WANDERS between random targets (visible stretch + squeeze; floor =
exactly touching, never colliding); when it reaches a border it JUMPS over the coyote (a parabolic
arc, flipping to face the other way mid-air) and the chase resumes the other way - and EACH border
event adds the next member of the chase train behind the coyote: SUPER MARIO first, then MORTY,
then MICKEY MOUSE, then a ROCKET, then (user 2026-10-18) six more drawn AT RANDOM per run from the EXTRAS
(Pac-Man, a ghost, Pikachu, Sonic, Kirby, SpongeBob, Tweety, Bugs Bunny) - a train of up to TRAIN_LEN, each
tailing the one ahead at its own wandering distance for the rest of the run. Drop-in compatible with the ttk.Progressbar calls the App makes:
`configure(mode=|maximum=|value=)`, `["value"]`, `start(interval)`, `stop()`. In determinate mode
(Run Pipeline) a thin accent PROGRESS UNDERLINE tracks the real per-phase value along the bottom
while the chase runs above it.

The sprites are two-frame pixel maps rendered ONCE into transparent tk.PhotoImages (right + left
facings); each tick only moves two canvas image items - no per-frame redraw of pixels. The chase
maths (`chase_step`, `jump_arc`) is pure and unit-tested without a display.

The motion is TIME-BASED (user 2026-10-10: "the animation during the running phases lags, can it be
smooth?"): a frame every FRAME_MS (~60 fps) moves the chase by the REAL time since the last frame -
every per-tick constant below is per TICK_S, the pace the user set - so a frame the busy UI thread
delivers late keeps the speed instead of stuttering it (a stall catches up at most MAX_STEP_S: no
teleport), and the steps are a third smaller than the old fixed 25 ms ticks. The whole chase - running,
jumping, the train, the leg gallop - runs at PACE (user 2026-10-18: "speed: 1/6") of the per-tick constants.
"""
from __future__ import annotations

import random
import time
import tkinter as tk

from pipeline5.workbench import theme

PIXEL = 2                     # sprite pixel size (px)
BAR_HEIGHT = 40               # tall enough for the FULL jump arc (apex sprite top stays on-canvas)
SPEED = 20.0                  # coyote px per tick (the user's 10x)
FOLLOWER_SPEED = 23.0         # a follower closes on the one ahead after a turn (slightly faster)
GAP_MIN, GAP_MAX = 0.0, 140.0  # the bird's lead between sprite EDGES (0 = head touches tail, never less)
GAP_RATE = 6.0                # px/tick the lead moves toward its current random target
RETARGET_P = 0.02             # per-tick chance the lead picks a new random target early
LAND_GAP = 30.0               # the lead right after a jump landing
JUMP_TICKS = 12               # jump duration (ticks) - snappy at the 10x pace
JUMP_LIFT = 17                # apex height (px) - clears the 16px coyote inside BAR_HEIGHT
MARGIN = 3                    # border padding (px)
FOLLOWER_GAP_LO, FOLLOWER_GAP_HI = 2.0, 50.0   # a follower's wandering distance behind its front
TICK_S = 0.025                # the reference tick every per-tick constant above is counted in (the pace)
FRAME_MS = 16                 # the frame interval (~60 fps) - each frame moves by the real time elapsed
GALLOP_S = 0.05               # one leg frame per 50 ms of chase time (two reference ticks)
MAX_STEP_S = 0.1              # a late frame catches up at most this much (a stall never teleports)
PACE = 1 / 6                  # the chase's speed vs the constants above (user 2026-10-18: "speed: 1/6")
TRAIN_LEN = 10                # the train's length: the four regulars + random EXTRAS (user 2026-10-18: "up to 10")

# --- the sprites (facing RIGHT; '.' transparent). Two frames each = the leg gallop. -------------- #
_RR_COLORS = {"P": "#5b6ee1", "Y": "#f4b41a"}                 # the bird: blue body, yellow legs/beak
_CY_COLORS = {"C": "#a0703c", "T": "#d8b98a"}                 # the coyote: brown, tan snout

ROADRUNNER = (
    ("...........PP...",
     "..........PPYY..",
     "P.........PP....",
     "PP......PPPP....",
     ".PPPPPPPPPP.....",
     "..PPPPPPPP......",
     "....YY..YY......",
     "...YY....YY....."),
    ("...........PP...",
     "..........PPYY..",
     "P.........PP....",
     "PP......PPPP....",
     ".PPPPPPPPPP.....",
     "..PPPPPPPP......",
     ".....Y..Y.......",
     "....YY...Y......"),
)
COYOTE = (
    (".C.........CC.....",
     ".CC....CCCCCCC....",
     "..CCCCCCCCCCCCTT..",
     "..CCCCCCCCCCCCT...",
     "...CCCCCCCCCCC....",
     "....CC......CC....",
     "....C........C....",
     "...CC.......CC...."),
    (".C.........CC.....",
     ".CC....CCCCCCC....",
     "..CCCCCCCCCCCCTT..",
     "..CCCCCCCCCCCCT...",
     "...CCCCCCCCCCC....",
     ".....CC....CC.....",
     "......C....C......",
     ".....CC....CC....."),
)
_MARIO_COLORS = {"R": "#e52521", "S": "#f7c59f", "B": "#2b5fce", "H": "#6b3e26"}
MARIO = (
    ("...RRRRR....",
     "..SSSSSS....",
     "..S.SS.S....",
     "...RRRR.....",
     ".RRBBBBRR...",
     ".SSBBBBSS...",
     "..BB..BB....",
     ".HH....HH..."),
    ("...RRRRR....",
     "..SSSSSS....",
     "..S.SS.S....",
     "...RRRR.....",
     ".RRBBBBRR...",
     ".SSBBBBSS...",
     "...BB.BB....",
     "..HH...HH..."),
)
_MORTY_COLORS = {"H": "#7a4a21", "S": "#f7d5a8", "Y": "#f4e04d", "J": "#3f5fbf"}
MORTY = (
    ("...HHHH.....",
     "..SSSSSS....",
     "..S.SS.S....",
     "..SSSSSS....",
     "...YYYY.....",
     ".SSYYYYSS...",
     "...JJ.JJ....",
     "..HH...HH..."),
    ("...HHHH.....",
     "..SSSSSS....",
     "..S.SS.S....",
     "..SSSSSS....",
     "...YYYY.....",
     ".SSYYYYSS...",
     "..JJ...JJ...",
     ".HH.....HH.."),
)
_MICKEY_COLORS = {"K": "#1a1a1a", "S": "#f7c59f", "R": "#e52521", "Y": "#f4b41a", "W": "#ffffff"}
MICKEY = (
    (".KK....KK...",
     ".KKK..KKK...",
     "..KKKKKK....",
     "..KSSSSK....",
     "...KKKK.....",
     "..RRWWRR....",
     "...KK.KK....",
     "..YY...YY..."),
    (".KK....KK...",
     ".KKK..KKK...",
     "..KKKKKK....",
     "..KSSSSK....",
     "...KKKK.....",
     "..RRWWRR....",
     "..KK...KK...",
     ".YY.....YY.."),
)
_ROCKET_COLORS = {"G": "#c8ccd4", "R": "#e52521", "O": "#ff9f1c", "W": "#9ad4ff"}
ROCKET = (
    ("................",
     ".....RR.........",
     "...O.GGGGGGGR...",
     "..OOOGGWWGGGRR..",
     "...O.GGGGGGGR...",
     ".....RR.........",
     "................",
     "................"),
    ("................",
     ".....RR.........",
     "..OO.GGGGGGGR...",
     ".OOOOGGWWGGGRR..",
     "..OO.GGGGGGGR...",
     ".....RR.........",
     "................",
     "................"),
)
# the border-event chase train, in JOIN ORDER: 1st border -> Mario, then Morty, Mickey, the rocket.
FOLLOWERS = ((MARIO, _MARIO_COLORS), (MORTY, _MORTY_COLORS),
             (MICKEY, _MICKEY_COLORS), (ROCKET, _ROCKET_COLORS))

# --- the EXTRAS: after the rocket, TRAIN_LEN - 4 of these join in a random order (a new draw per run) --- #
_PACMAN_COLORS = {"Y": "#ffd400", "K": "#1a1a1a"}
PACMAN = (
    ("....YYYY....",
     "..YYYYYYYY..",
     ".YYYYKYY....",
     ".YYYYY......",
     ".YYYYY......",
     ".YYYYYYY....",
     "..YYYYYYYY..",
     "....YYYY...."),
    ("....YYYY....",
     "..YYYYYYYY..",
     ".YYYYKYYYYY.",
     ".YYYYYYYYYY.",
     ".YYYYYYYYYY.",
     ".YYYYYYYYYY.",
     "..YYYYYYYY..",
     "....YYYY...."),
)
_GHOST_COLORS = {"R": "#e52521", "W": "#ffffff", "B": "#2b5fce"}
GHOST = (
    ("....RRRR....",
     "..RRRRRRRR..",
     ".RRRWBRRWBR.",
     ".RRRWWRRWWR.",
     ".RRRRRRRRRR.",
     ".RRRRRRRRRR.",
     ".RRRRRRRRRR.",
     ".R.RR.RR.RR."),
    ("....RRRR....",
     "..RRRRRRRR..",
     ".RRRWBRRWBR.",
     ".RRRWWRRWWR.",
     ".RRRRRRRRRR.",
     ".RRRRRRRRRR.",
     ".RRRRRRRRRR.",
     ".RR.RR.RR.R."),
)
_PIKACHU_COLORS = {"Y": "#f8d030", "K": "#1a1a1a", "R": "#e52521", "N": "#a0703c"}
PIKACHU = (
    ("...K....K...",
     "...Y....Y...",
     "...YYYYYY...",
     "N..YYYKYK...",
     "NN.RYYYYR...",
     ".NNYYYYYY...",
     "...YYYYYY...",
     "...YY...Y..."),
    ("...K....K...",
     "...Y....Y...",
     "...YYYYYY...",
     "N..YYYKYK...",
     "NN.RYYYYR...",
     ".NNYYYYYY...",
     "...YYYYYY...",
     "....Y..YY..."),
)
_SONIC_COLORS = {"B": "#1f5fd6", "S": "#f7c59f", "W": "#ffffff", "K": "#1a1a1a", "R": "#e52521"}
SONIC = (
    ("..BBBBB.....",
     "BBBBBBBB....",
     "..BBBBWWK...",
     "BBBBBBSSS...",
     "..BBBBSS....",
     "...SBBBS....",
     "...BB..BB...",
     "..RR....RR.."),
    ("..BBBBB.....",
     "BBBBBBBB....",
     "..BBBBWWK...",
     "BBBBBBSSS...",
     "..BBBBSS....",
     "...SBBBS....",
     "....BBB.....",
     "...RR.RR...."),
)
_KIRBY_COLORS = {"P": "#f7a1c4", "K": "#1a1a1a", "R": "#d62d4a"}
KIRBY = (
    ("............",
     "....PPPP....",
     "..PPPPPPPP..",
     "..PPPPKPKP..",
     "..PPPPKPKP..",
     "..PPPPPPPP..",
     "...PPPPPP...",
     "..RRR..RRR.."),
    ("............",
     "....PPPP....",
     "..PPPPPPPP..",
     "..PPPPKPKP..",
     "..PPPPKPKP..",
     "..PPPPPPPP..",
     "...PPPPPP...",
     "...RRR.RRR.."),
)
_SPONGEBOB_COLORS = {"Y": "#f4e04d", "W": "#ffffff", "B": "#2b5fce", "K": "#1a1a1a", "N": "#8a5a2b"}
SPONGEBOB = (
    (".YYYYYYYYY..",
     ".YYWBYYWBY..",
     ".YYWWYYWWY..",
     ".YYYYYYYYY..",
     ".YYYKKKYYY..",
     ".NNNNNNNNN..",
     "...Y...Y....",
     "..KK..KK...."),
    (".YYYYYYYYY..",
     ".YYWBYYWBY..",
     ".YYWWYYWWY..",
     ".YYYYYYYYY..",
     ".YYYKKKYYY..",
     ".NNNNNNNNN..",
     "....Y.Y.....",
     "...KK.KK...."),
)
_TWEETY_COLORS = {"Y": "#ffd93b", "B": "#2b5fce", "O": "#ff9f1c"}
TWEETY = (
    ("....YYYY....",
     "...YYYYYY...",
     "...YYYBYB...",
     "...YYYYYOO..",
     "....YYYY....",
     "...YYYYYY...",
     "....O..O....",
     "...OO.OO...."),
    ("....YYYY....",
     "...YYYYYY...",
     "...YYYBYB...",
     "...YYYYYOO..",
     "....YYYY....",
     "...YYYYYY...",
     ".....OO.....",
     "....OOOO...."),
)
_BUGS_COLORS = {"G": "#9aa0a8", "P": "#f7a1c4", "W": "#ffffff", "K": "#1a1a1a"}
BUGS = (
    ("...GG..GG...",
     "...GP..GP...",
     "...GG..GG...",
     "..GGGGGGG...",
     "..GGGWKGWK..",
     "..GGWWWWWW..",
     "...GGGGG....",
     "..WW...WW..."),
    ("...GG..GG...",
     "...GP..GP...",
     "...GG..GG...",
     "..GGGGGGG...",
     "..GGGWKGWK..",
     "..GGWWWWWW..",
     "...GGGGG....",
     "...WW.WW...."),
)
EXTRAS = ((PACMAN, _PACMAN_COLORS), (GHOST, _GHOST_COLORS), (PIKACHU, _PIKACHU_COLORS),
          (SONIC, _SONIC_COLORS), (KIRBY, _KIRBY_COLORS), (SPONGEBOB, _SPONGEBOB_COLORS),
          (TWEETY, _TWEETY_COLORS), (BUGS, _BUGS_COLORS))


def pick_train(sample=random.sample) -> list:
    """One run's chase train in JOIN ORDER: the four regulars (FOLLOWERS), then TRAIN_LEN - 4 of the EXTRAS
    drawn at random, none twice (user 2026-10-18: "add more random cartoon characters after the last one (up
    to 10)"). `sample(population, k)` is random.sample's contract."""
    return list(FOLLOWERS) + list(sample(list(EXTRAS), TRAIN_LEN - len(FOLLOWERS)))


def sprite_size(frames) -> tuple:
    """(width, height) of a sprite in PIXELS (all frames/rows must agree - the tests enforce it)."""
    return len(frames[0][0]) * PIXEL, len(frames[0]) * PIXEL


def jump_arc(t: float) -> float:
    """The parabolic lift factor for jump progress t in [0,1]: 0 at take-off/landing, 1 at apex."""
    return 4.0 * t * (1.0 - t)


def chase_step(state: dict, width: float, rand, k: float = 1.0) -> dict:
    """One pure animation step of `k` reference ticks (k = elapsed / TICK_S; 1.0 = one tick - every
    per-tick rate scales by it, a per-tick chance becomes 1 - (1 - p)**k). `state`: dir (+1 right / -1 left),
    cx (coyote centre), gap + gap_t
    (the bird's lead and its current random TARGET), rw/cw (sprite widths), fw (the follower
    widths, in join order - the train's capacity), followers ([{x, gap}] - the border-event chase train so far), and the
    jump fields (jump = None or the 0..1 progress; jump_from/jump_to = the arc endpoints).
    `rand()` -> [0,1).

    Chasing: the coyote runs at SPEED; the bird's lead WANDERS between random targets in
    [GAP_MIN, GAP_MAX] at GAP_RATE (visible stretch + squeeze; 0 = the coyote's head touching the
    bird's tail - never less, they never collide); the bird rides at cx + dir*(half-spans + gap).
    Border: the bird takes off - the coyote SKIDS (freezes, and the whole train with it) while the
    bird arcs over it to a landing BEHIND it; on landing all reverse, and EACH landing (up to
    len(fw)) spawns the NEXT follower at the border the bird just left - Mario, then Morty, then
    Mickey, then the rocket, then the run's random extras - each tailing the one ahead at its own wandering
    distance."""
    s = dict(state)
    s["followers"] = [dict(f) for f in state.get("followers", [])]
    spans = s["cw"] / 2 + s["rw"] / 2
    if s["jump"] is not None:                     # mid-air: only the arc progresses
        t = s["jump"] + k / JUMP_TICKS
        if t >= 1.0:                              # landed: reverse the chase
            old_dir = s["dir"]
            s["dir"] = -old_dir
            s["gap"] = s["gap_t"] = LAND_GAP
            s["rx"] = s["jump_to"]
            s["jump"] = None
            n = len(s["followers"])
            if n < len(s["fw"]):                  # the border event: the NEXT follower joins the train
                border = (width - MARGIN - s["fw"][n] / 2) if old_dir > 0 else (MARGIN + s["fw"][n] / 2)
                s["followers"].append({"x": border, "gap": 20.0})
        else:
            s["jump"] = t
        return s
    # the bird's lead wanders between random targets - visibly stretching and squeezing
    rate = GAP_RATE * k
    if abs(s["gap"] - s["gap_t"]) < rate or rand() < 1.0 - (1.0 - RETARGET_P) ** k:
        s["gap_t"] = GAP_MIN + rand() * (GAP_MAX - GAP_MIN)
    s["gap"] += max(-rate, min(rate, s["gap_t"] - s["gap"]))
    s["gap"] = max(GAP_MIN, min(GAP_MAX, s["gap"]))
    s["cx"] += s["dir"] * SPEED * k
    s["cx"] = max(MARGIN + s["cw"] / 2, min(width - MARGIN - s["cw"] / 2, s["cx"]))
    rx = s["cx"] + s["dir"] * (spans + s["gap"])
    hi, lo = width - MARGIN - s["rw"] / 2, MARGIN + s["rw"] / 2
    if (s["dir"] > 0 and rx >= hi) or (s["dir"] < 0 and rx <= lo):
        s["jump"] = 0.0                           # take off from the border...
        s["jump_from"] = max(lo, min(hi, rx))
        s["jump_to"] = s["cx"] - s["dir"] * (spans + LAND_GAP)   # ...over the coyote, landing behind
        rx = s["jump_from"]
    s["rx"] = rx
    # the train: each follower tails the one AHEAD of it at its own wandering gap
    front_x, front_w = s["cx"], s["cw"]
    for i, follower in enumerate(s["followers"]):
        follower["gap"] = max(FOLLOWER_GAP_LO,
                              min(FOLLOWER_GAP_HI, follower["gap"] + (rand() * 6.0 - 3.0) * k))
        target = front_x - s["dir"] * (front_w / 2 + s["fw"][i] / 2 + follower["gap"])
        step = FOLLOWER_SPEED * k
        follower["x"] += max(-step, min(step, target - follower["x"]))
        front_x, front_w = follower["x"], s["fw"][i]
    return s


def _build_image(root, frames, colors, mirrored: bool):
    """One transparent PhotoImage per frame (pixels put at PIXEL scale; unset pixels stay clear)."""
    out = []
    for frame in frames:
        rows = [row[::-1] for row in frame] if mirrored else list(frame)
        photo = tk.PhotoImage(master=root, width=len(rows[0]) * PIXEL, height=len(rows) * PIXEL)
        for y, row in enumerate(rows):
            for x, ch in enumerate(row):
                if ch in colors:
                    photo.put(colors[ch], to=(x * PIXEL, y * PIXEL, (x + 1) * PIXEL, (y + 1) * PIXEL))
        out.append(photo)
    return out


class ChaseBar(tk.Canvas):
    """The animated strip. `start(interval)` runs the chase (indeterminate AND determinate - a
    Run-Pipeline shows the chase plus the accent progress underline); `stop()` idles it (sprites
    parked off-canvas). Follows the theme via `set_theme`."""

    def __init__(self, parent, mode: str = "dark", **kw):
        super().__init__(parent, height=BAR_HEIGHT, highlightthickness=0, **kw)
        self._mode = "indeterminate"
        self._max = 100.0
        self._value = 0.0
        self._job = None
        self._interval = FRAME_MS
        self._last = None             # the previous frame's time (perf_counter) - the step's real dt
        rw, _rh = sprite_size(ROADRUNNER)
        cw, _ch = sprite_size(COYOTE)
        self._state = {"dir": 1, "cx": 120.0, "gap": 30.0, "gap_t": 30.0, "rx": 180.0,
                       "rw": float(rw), "cw": float(cw), "fw": [], "followers": [], "jump": None}
        # facing index 0 = right, 1 = left (mirrored pixel maps)
        self._rr_img = (_build_image(self, ROADRUNNER, _RR_COLORS, False),
                        _build_image(self, ROADRUNNER, _RR_COLORS, True))
        self._cy_img = (_build_image(self, COYOTE, _CY_COLORS, False),
                        _build_image(self, COYOTE, _CY_COLORS, True))
        self._imgs = {frames: (_build_image(self, frames, colors, False),     # every possible member, once
                               _build_image(self, frames, colors, True)) for frames, colors in FOLLOWERS + EXTRAS}
        self._train_imgs = []
        self._pick_train()
        self._ground_y = BAR_HEIGHT - 6
        self._fill = self.create_rectangle(0, BAR_HEIGHT - 4, 0, BAR_HEIGHT, width=0)
        self._ground = self.create_line(0, self._ground_y + 1, 4000, self._ground_y + 1)
        self._f_items = [self.create_image(-100, self._ground_y, anchor="s",   # under the coyote's z
                                           image=self._train_imgs[i][0][0]) for i in range(TRAIN_LEN)]
        self._cy_item = self.create_image(-100, self._ground_y, anchor="s",
                                          image=self._cy_img[0][0])
        self._rr_item = self.create_image(-100, self._ground_y, anchor="s",
                                          image=self._rr_img[0][0])
        self.set_theme(mode)

    # --- the ttk.Progressbar-compatible surface --------------------------------------------------- #
    def configure(self, cnf=None, **kw):
        if cnf:
            kw = {**cnf, **kw}
        if "mode" in kw:
            self._mode = str(kw.pop("mode"))
        if "maximum" in kw:
            self._max = max(1.0, float(kw.pop("maximum")))
        if "value" in kw:
            self._value = float(kw.pop("value"))
            self._draw_fill()
        if kw:
            return super().configure(**kw)

    config = configure

    def __getitem__(self, key):
        if key in ("value", "maximum", "mode"):
            return {"value": self._value, "maximum": self._max, "mode": self._mode}[key]
        return super().__getitem__(key)

    def start(self, interval: int = FRAME_MS) -> None:
        """Begin a FRESH chase (both modes; determinate keeps its real progress underline) - a frame every
        `interval` ms, never faster than FRAME_MS. The follower train waits for its border entrances again
        on every new run - its random extras drawn anew."""
        self._interval = max(FRAME_MS, int(interval))
        if self._job is None:
            self._last = None
            self._pick_train()
            self._state.update(cx=max(60.0, self.winfo_width() * 0.3 or 120.0),
                               dir=1, jump=None, gap=30.0, gap_t=30.0, followers=[])
            self._job = self.after(self._interval, self._tick)

    def stop(self) -> None:
        if self._job is not None:
            self.after_cancel(self._job)
            self._job = None
        for item in (self._rr_item, self._cy_item, *self._f_items):  # park the runners off-canvas
            self.coords(item, -100, self._ground_y)
        self._value = 0.0
        self._draw_fill()

    def _pick_train(self) -> None:
        """Draw this run's train (`pick_train`): its members' images per slot and their widths (the capacity)."""
        train = pick_train()
        self._train_imgs = [self._imgs[frames] for frames, _c in train]
        self._state["fw"] = [float(sprite_size(frames)[0]) for frames, _c in train]

    # --- the animation ----------------------------------------------------------------------------- #
    def _tick(self) -> None:
        if not self.winfo_exists():
            self._job = None
            return
        now = time.perf_counter()
        dt = 0.0 if self._last is None else min(MAX_STEP_S, max(0.0, now - self._last))
        self._last = now
        width = float(max(self.winfo_width(), 160))
        in_jump = self._state["jump"] is not None
        self._state = chase_step(self._state, width, random.random, dt / TICK_S * PACE)
        s = self._state
        frame = int(now * PACE / GALLOP_S) % 2    # the gallop runs on the clock (at PACE), not the frame count
        facing = 0 if s["dir"] > 0 else 1
        if s["jump"] is not None:                  # mid-air: interpolate the arc; the coyote skids
            t = s["jump"]
            rx = s["jump_from"] + (s["jump_to"] - s["jump_from"]) * t
            ry = self._ground_y - JUMP_LIFT * jump_arc(t)
            rr_facing = facing if t < 0.5 else 1 - facing      # flips mid-air to face the new way
            self.itemconfigure(self._rr_item, image=self._rr_img[rr_facing][0])
            self.coords(self._rr_item, rx, ry)
            self.itemconfigure(self._cy_item, image=self._cy_img[facing][0])
            self.coords(self._cy_item, s["cx"], self._ground_y)
        else:
            if in_jump:                            # just landed: both now face the new direction
                facing = 0 if s["dir"] > 0 else 1
            self.itemconfigure(self._rr_item, image=self._rr_img[facing][frame])
            self.coords(self._rr_item, s["rx"], self._ground_y)
            self.itemconfigure(self._cy_item, image=self._cy_img[facing][frame])
            self.coords(self._cy_item, s["cx"], self._ground_y)
        for i, follower in enumerate(s["followers"]):   # the train (frozen while the coyote skids)
            self.itemconfigure(self._f_items[i],
                               image=self._train_imgs[i][facing][0 if s["jump"] is not None else frame])
            self.coords(self._f_items[i], follower["x"], self._ground_y)
        self.tag_raise(self._rr_item)              # the bird passes OVER the coyote
        spent_ms = int((time.perf_counter() - now) * 1000)
        self._job = self.after(max(1, self._interval - spent_ms), self._tick)

    def _draw_fill(self) -> None:
        """The determinate progress underline (bottom 4px, accent) - hidden at value 0."""
        width = float(max(self.winfo_width(), 160))
        frac = max(0.0, min(1.0, self._value / self._max)) if self._mode == "determinate" else 0.0
        self.coords(self._fill, 0, BAR_HEIGHT - 4, width * frac, BAR_HEIGHT)

    def set_theme(self, mode: str) -> None:
        c = theme.TOKENS["dark" if mode == "dark" else "light"]
        super().configure(bg=c["bg"])
        self.itemconfigure(self._ground, fill=c["grid_line"])
        self.itemconfigure(self._fill, fill=c["accent"])
