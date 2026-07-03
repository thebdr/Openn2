"""The busy/progress strip as a PIXEL CHASE: a coyote chasing a roadrunner back and forth across
the bar. The roadrunner's lead grows and shrinks RANDOMLY; when it reaches a border it JUMPS over
the coyote (a parabolic arc, flipping to face the other way mid-air) and the chase resumes in the
opposite direction. Drop-in compatible with the ttk.Progressbar calls the App makes:
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
SPEED = 2.0                   # coyote px per tick
GAP_MIN, GAP_MAX = 8.0, 80.0  # the roadrunner's lead (px between sprite edges)
LAND_GAP = 30.0               # the lead right after a jump landing
JUMP_TICKS = 26               # jump duration (ticks)
JUMP_LIFT = 17                # apex height (px) - clears the 16px coyote inside BAR_HEIGHT
MARGIN = 3                    # border padding (px)

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


def sprite_size(frames) -> tuple:
    """(width, height) of a sprite in PIXELS (all frames/rows must agree - the tests enforce it)."""
    return len(frames[0][0]) * PIXEL, len(frames[0]) * PIXEL


def jump_arc(t: float) -> float:
    """The parabolic lift factor for jump progress t in [0,1]: 0 at take-off/landing, 1 at apex."""
    return 4.0 * t * (1.0 - t)


def chase_step(state: dict, width: float, rand) -> dict:
    """One pure animation tick. `state`: dir (+1 right / -1 left), cx (coyote centre), gap (the
    roadrunner's random-walk lead), rw/cw (sprite widths), and the jump fields (jump = None or the
    0..1 progress; jump_from/jump_to = the arc endpoints). `rand()` -> [0,1).

    Chasing: the coyote runs at SPEED; the lead drifts randomly within [GAP_MIN, GAP_MAX]; the
    roadrunner rides at cx + dir*(half-spans + gap). Border: the roadrunner takes off - the coyote
    SKIDS (freezes) while the bird arcs over it to a landing BEHIND it; on landing both reverse."""
    s = dict(state)
    spans = s["cw"] / 2 + s["rw"] / 2
    if s["jump"] is not None:                     # mid-air: only the arc progresses
        t = s["jump"] + 1.0 / JUMP_TICKS
        if t >= 1.0:                              # landed: reverse the chase
            s["dir"] = -s["dir"]
            s["gap"] = LAND_GAP
            s["rx"] = s["jump_to"]
            s["jump"] = None
        else:
            s["jump"] = t
        return s
    s["gap"] = max(GAP_MIN, min(GAP_MAX, s["gap"] + (rand() * 4.0 - 1.8)))
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
        self._state = {"dir": 1, "cx": 120.0, "gap": 30.0, "rx": 180.0,
                       "rw": float(rw), "cw": float(cw), "jump": None}
        # facing index 0 = right, 1 = left (mirrored pixel maps)
        self._rr_img = (_build_image(self, ROADRUNNER, _RR_COLORS, False),
                        _build_image(self, ROADRUNNER, _RR_COLORS, True))
        self._cy_img = (_build_image(self, COYOTE, _CY_COLORS, False),
                        _build_image(self, COYOTE, _CY_COLORS, True))
        self._ground_y = BAR_HEIGHT - 6
        self._fill = self.create_rectangle(0, BAR_HEIGHT - 4, 0, BAR_HEIGHT, width=0)
        self._ground = self.create_line(0, self._ground_y + 1, 4000, self._ground_y + 1)
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
        """Begin the chase (both modes; determinate keeps its real progress underline)."""
        self._interval = max(25, int(interval))
        if self._job is None:
            self._state["cx"] = max(60.0, self.winfo_width() * 0.3 or 120.0)
            self._state["dir"], self._state["jump"] = 1, None
            self._job = self.after(self._interval, self._tick)

    def stop(self) -> None:
        if self._job is not None:
            self.after_cancel(self._job)
            self._job = None
        self.coords(self._rr_item, -100, self._ground_y)      # park the runners off-canvas
        self.coords(self._cy_item, -100, self._ground_y)
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
        frame = (self._ticks // 3) % 2
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
