"""The busy/progress strip as a PIXEL CHASE: a coyote chasing a roadrunner back and forth across
the bar. The roadrunner's lead WANDERS between random targets (visible stretch + squeeze; floor =
exactly touching, never colliding); when it reaches a border it JUMPS over the coyote (a parabolic
arc, flipping to face the other way mid-air) and the chase resumes the other way - and the FIRST
border event brings SUPER MARIO in behind the coyote, tailing it at his own wandering distance for
the rest of the run. Drop-in compatible with the ttk.Progressbar calls the App makes:
`configure(mode=|maximum=|value=)`, `["value"]`, `start(interval)`, `stop()`. In determinate mode
(Run Pipeline) a thin accent PROGRESS UNDERLINE tracks the real per-phase value along the bottom
while the chase runs above it.

The sprites are two-frame pixel maps rendered ONCE into transparent tk.PhotoImages (right + left
facings); each tick only moves two canvas image items - no per-frame redraw of pixels. The chase
maths (`chase_step`, `jump_arc`) is pure and unit-tested without a display.
"""
from __future__ import annotations

import random
import tkinter as tk

from pipeline4.gui import theme

PIXEL = 2                     # sprite pixel size (px)
BAR_HEIGHT = 40               # tall enough for the FULL jump arc (apex sprite top stays on-canvas)
SPEED = 20.0                  # coyote px per tick (the user's 10x)
MARIO_SPEED = 23.0            # Mario closes on the coyote after a turn (slightly faster)
GAP_MIN, GAP_MAX = 0.0, 140.0  # the bird's lead between sprite EDGES (0 = head touches tail, never less)
GAP_RATE = 6.0                # px/tick the lead moves toward its current random target
RETARGET_P = 0.02             # per-tick chance the lead picks a new random target early
LAND_GAP = 30.0               # the lead right after a jump landing
JUMP_TICKS = 12               # jump duration (ticks) - snappy at the 10x pace
JUMP_LIFT = 17                # apex height (px) - clears the 16px coyote inside BAR_HEIGHT
MARGIN = 3                    # border padding (px)
MARIO_GAP_LO, MARIO_GAP_HI = 2.0, 50.0   # Mario's wandering distance behind the coyote

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


def sprite_size(frames) -> tuple:
    """(width, height) of a sprite in PIXELS (all frames/rows must agree - the tests enforce it)."""
    return len(frames[0][0]) * PIXEL, len(frames[0]) * PIXEL


def jump_arc(t: float) -> float:
    """The parabolic lift factor for jump progress t in [0,1]: 0 at take-off/landing, 1 at apex."""
    return 4.0 * t * (1.0 - t)


def chase_step(state: dict, width: float, rand) -> dict:
    """One pure animation tick. `state`: dir (+1 right / -1 left), cx (coyote centre), gap + gap_t
    (the bird's lead and its current random TARGET), rw/cw/mw (sprite widths), mx/mgap (Mario -
    None until his border entrance), and the jump fields (jump = None or the 0..1 progress;
    jump_from/jump_to = the arc endpoints). `rand()` -> [0,1).

    Chasing: the coyote runs at SPEED; the bird's lead WANDERS between random targets in
    [GAP_MIN, GAP_MAX] at GAP_RATE (visible stretch + squeeze; 0 = the coyote's head touching the
    bird's tail - never less, they never collide); the bird rides at cx + dir*(half-spans + gap).
    Border: the bird takes off - the coyote SKIDS (freezes) while the bird arcs over it to a
    landing BEHIND it; on landing both reverse, and the FIRST landing spawns SUPER MARIO at the
    border the bird just left, chasing the coyote from behind at his own wandering distance."""
    s = dict(state)
    spans = s["cw"] / 2 + s["rw"] / 2
    if s["jump"] is not None:                     # mid-air: only the arc progresses
        t = s["jump"] + 1.0 / JUMP_TICKS
        if t >= 1.0:                              # landed: reverse the chase
            old_dir = s["dir"]
            s["dir"] = -old_dir
            s["gap"] = s["gap_t"] = LAND_GAP
            s["rx"] = s["jump_to"]
            s["jump"] = None
            if s.get("mx") is None:               # the border event: Mario enters behind the coyote
                s["mx"] = (width - MARGIN - s["mw"] / 2) if old_dir > 0 else (MARGIN + s["mw"] / 2)
                s["mgap"] = 20.0
        else:
            s["jump"] = t
        return s
    # the bird's lead wanders between random targets - visibly stretching and squeezing
    if abs(s["gap"] - s["gap_t"]) < GAP_RATE or rand() < RETARGET_P:
        s["gap_t"] = GAP_MIN + rand() * (GAP_MAX - GAP_MIN)
    s["gap"] += max(-GAP_RATE, min(GAP_RATE, s["gap_t"] - s["gap"]))
    s["gap"] = max(GAP_MIN, min(GAP_MAX, s["gap"]))
    s["cx"] += s["dir"] * SPEED
    s["cx"] = max(MARGIN + s["cw"] / 2, min(width - MARGIN - s["cw"] / 2, s["cx"]))
    rx = s["cx"] + s["dir"] * (spans + s["gap"])
    hi, lo = width - MARGIN - s["rw"] / 2, MARGIN + s["rw"] / 2
    if (s["dir"] > 0 and rx >= hi) or (s["dir"] < 0 and rx <= lo):
        s["jump"] = 0.0                           # take off from the border...
        s["jump_from"] = max(lo, min(hi, rx))
        s["jump_to"] = s["cx"] - s["dir"] * (spans + LAND_GAP)   # ...over the coyote, landing behind
        rx = s["jump_from"]
    s["rx"] = rx
    if s.get("mx") is not None:                   # Mario tails the coyote at his own wandering gap
        s["mgap"] = max(MARIO_GAP_LO, min(MARIO_GAP_HI, s["mgap"] + (rand() * 6.0 - 3.0)))
        target = s["cx"] - s["dir"] * (s["cw"] / 2 + s["mw"] / 2 + s["mgap"])
        s["mx"] += max(-MARIO_SPEED, min(MARIO_SPEED, target - s["mx"]))
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
        self._interval = 30
        self._ticks = 0
        rw, _rh = sprite_size(ROADRUNNER)
        cw, _ch = sprite_size(COYOTE)
        mw, _mh = sprite_size(MARIO)
        self._state = {"dir": 1, "cx": 120.0, "gap": 30.0, "gap_t": 30.0, "rx": 180.0,
                       "rw": float(rw), "cw": float(cw), "mw": float(mw),
                       "mx": None, "mgap": 20.0, "jump": None}
        # facing index 0 = right, 1 = left (mirrored pixel maps)
        self._rr_img = (_build_image(self, ROADRUNNER, _RR_COLORS, False),
                        _build_image(self, ROADRUNNER, _RR_COLORS, True))
        self._cy_img = (_build_image(self, COYOTE, _CY_COLORS, False),
                        _build_image(self, COYOTE, _CY_COLORS, True))
        self._m_img = (_build_image(self, MARIO, _MARIO_COLORS, False),
                       _build_image(self, MARIO, _MARIO_COLORS, True))
        self._ground_y = BAR_HEIGHT - 6
        self._fill = self.create_rectangle(0, BAR_HEIGHT - 4, 0, BAR_HEIGHT, width=0)
        self._ground = self.create_line(0, self._ground_y + 1, 4000, self._ground_y + 1)
        self._m_item = self.create_image(-100, self._ground_y, anchor="s",   # under the coyote's z
                                         image=self._m_img[0][0])
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

    def start(self, interval: int = 30) -> None:
        """Begin a FRESH chase (both modes; determinate keeps its real progress underline).
        Mario waits for his border entrance again on every new run."""
        self._interval = max(25, int(interval))
        if self._job is None:
            self._state.update(cx=max(60.0, self.winfo_width() * 0.3 or 120.0),
                               dir=1, jump=None, gap=30.0, gap_t=30.0, mx=None, mgap=20.0)
            self._job = self.after(self._interval, self._tick)

    def stop(self) -> None:
        if self._job is not None:
            self.after_cancel(self._job)
            self._job = None
        for item in (self._rr_item, self._cy_item, self._m_item):   # park the runners off-canvas
            self.coords(item, -100, self._ground_y)
        self._value = 0.0
        self._draw_fill()

    # --- the animation ----------------------------------------------------------------------------- #
    def _tick(self) -> None:
        if not self.winfo_exists():
            self._job = None
            return
        self._ticks += 1
        width = float(max(self.winfo_width(), 160))
        in_jump = self._state["jump"] is not None
        self._state = chase_step(self._state, width, random.random)
        s = self._state
        frame = (self._ticks // 2) % 2             # fast gallop to match the 10x pace
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
        if s.get("mx") is not None:                # Mario tails the coyote (frozen while it skids)
            self.itemconfigure(self._m_item,
                               image=self._m_img[facing][0 if s["jump"] is not None else frame])
            self.coords(self._m_item, s["mx"], self._ground_y)
        self.tag_raise(self._rr_item)              # the bird passes OVER the coyote
        self._job = self.after(self._interval, self._tick)

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
