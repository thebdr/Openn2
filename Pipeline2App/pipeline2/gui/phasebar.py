"""phasebar.py - the horizontal phase-button bar + chevron dropdown popups.

Layout (matches assets/ButtonsLayout.xlsx): a top row of phase-header buttons separated by ">",
with the pink "Run Pipeline" master on the left. Clicking a phase header RUNS the whole phase.
Beneath each header is a grey chevron button; clicking it opens an anchored, scrollable dropdown
listing that phase's individual buttons - white "action" steps (a cascade with `˅` arrows between
them), light-blue "open file/folder" buttons, and the occasional orange "special". The dropdown is
positioned just under the chevron, capped to the window height (scrollbar past the cap), and closes
on Escape, on a click outside it, or when another chevron is clicked.

UI-only: the caller (gui.py / gui_designer.py) supplies a declarative phase spec whose button
`command`s are ready-to-call callables (actions already wrapped in the worker-thread `_start`,
opens calling `_open_path`, disabled stubs with `command=None`). Button colours come from the
semantic ttk styles registered in theme.apply_ttk.
"""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk

from pipeline2.gui import theme

_CHEVRON = "▼"          # opens the popup (a clear down-arrow icon)
_CASCADE = "˅"          # ˅  (between sequential action steps)
# the phase headers, the chevron under each, AND the dropdown buttons all share this width: the
# headers are ~6/10 of their old single-line width and the popup buttons match them. Labels word-wrap
# to fit, so everything is one tidy column width.
_BTN_WIDTH = 12          # = the header/popup button width (characters)


def _wrap(text: str, width: int) -> str:
    """Greedily word-wrap `text` so each line is <= `width` characters (a word longer than `width`
    still gets its own line). Keeps the button to ~`width` chars wide."""
    lines, cur = [], ""
    for word in text.split():
        if cur and len(cur) + 1 + len(word) > width:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}" if cur else word
    if cur:
        lines.append(cur)
    return "\n".join(lines)
_HEADER_H = 60          # phase-header row height (~double a single-line button)
_CHEVRON_H = 19         # chevron row height (a short strip)
_GAP_H = 18             # uniform height of the inter-button gap (˅ arrow or divider)

_KIND_STYLE = {
    "action": "Action.TButton",
    "open": "Open.TButton",
    "special": "Special.TButton",
    "disabled": "Disabled.TButton",
}


def _gap(parent, arrow: bool):
    """A fixed-height row between two dropdown buttons: a `˅` cascade arrow between sequential action
    steps, otherwise a horizontal divider - both the SAME height for an even vertical rhythm."""
    g = ttk.Frame(parent, height=_GAP_H)
    g.pack_propagate(False)
    if arrow:
        ttk.Label(g, text=_CASCADE, anchor="center").pack(fill="both", expand=True)
    else:
        ttk.Separator(g, orient="horizontal").pack(fill="x", expand=True, padx=10)
    g.pack(fill="x")


def _scrollable(parent, bg: str):
    """A vertically scrollable region -> (outer, canvas, scrollbar, inner). The caller packs the
    canvas/scrollbar and sizes the canvas; `inner` holds the content."""
    outer = ttk.Frame(parent)
    canvas = tk.Canvas(outer, highlightthickness=0, background=bg)
    vs = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=vs.set)
    inner = ttk.Frame(canvas)
    win = canvas.create_window((0, 0), window=inner, anchor="nw")
    inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win, width=e.width))
    canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>",
                                                     lambda ev: canvas.yview_scroll(int(-ev.delta / 120), "units")))
    canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))
    return outer, canvas, vs, inner


class _Dropdown(tk.Toplevel):
    """An anchored, scrollable, click-away-to-close popup of a phase's buttons."""

    def __init__(self, root, anchor, buttons, ignore, on_close):
        super().__init__(root)
        self.withdraw()                       # build off-screen, show only once positioned (no corner flash)
        self._owner = root                    # NB: never name this `_root` - it shadows a tk method
        self._ignore = ignore                 # chevron widgets - their clicks toggle, not close
        self._on_close = on_close
        self._closed = False
        self.overrideredirect(True)
        try:
            self.attributes("-topmost", True)
        except tk.TclError:
            pass

        bg = theme.palette(_is_dark(root))["bg"]
        border = ttk.Frame(self, relief="solid", borderwidth=1)
        border.pack(fill="both", expand=True)
        outer, canvas, vs, inner = _scrollable(border, bg)

        prev_kind = None
        for spec in buttons:
            kind = spec.get("kind", "action")
            if prev_kind is not None:          # uniform-height gap between every pair of buttons
                _gap(inner, arrow=(prev_kind == "action" and kind == "action"))
            b = ttk.Button(inner, text=_wrap(spec["label"], _BTN_WIDTH), width=_BTN_WIDTH,
                           style=_KIND_STYLE.get(kind, "Action.TButton"),
                           command=lambda s=spec: self._fire(s))
            if kind == "disabled" or not spec.get("command"):
                b.state(["disabled"])
            b.pack(fill="x")
            prev_kind = kind

        # position under the chevron, cap the height to the window bottom, show the scrollbar past it
        self.update_idletasks()
        x = anchor.winfo_rootx()
        y = anchor.winfo_rooty() + anchor.winfo_height()
        content_h = inner.winfo_reqheight()
        cap = max(140, (root.winfo_rooty() + root.winfo_height()) - y - 10)
        h = min(content_h, cap)
        # the popup is exactly the chevron/header column width, so the buttons match the main ones
        # (the header font is bold, so equal char-widths render wider - match pixels instead)
        canvas.configure(height=h, width=max(anchor.winfo_width(), inner.winfo_reqwidth()))
        if content_h > cap:
            vs.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        outer.pack(fill="both", expand=True)
        # clamp to the screen so a right-edge chevron's popup doesn't spill off, then show it
        self.update_idletasks()
        x = max(0, min(x, self.winfo_screenwidth() - self.winfo_reqwidth() - 4))
        self.geometry(f"+{x}+{y}")
        self.deiconify()
        self.lift()

        self.bind("<Escape>", lambda e: self.close())
        root.bind_all("<Button-1>", self._maybe_close, "+")

    def _fire(self, spec):
        cmd = spec.get("command")
        self.close()
        if cmd:
            cmd()

    def _maybe_close(self, event):
        if self._closed:
            return
        if event.widget in self._ignore:               # a chevron toggles via its own command
            return
        # keep the popup open while the click is inside it (walk the widget tree, not coordinates -
        # coordinate math breaks under display scaling: event.x_root is physical px, winfo_* logical px)
        w = event.widget
        while w is not None:
            if w is self:
                return
            w = getattr(w, "master", None)
        self.close()

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            self._owner.unbind_all("<MouseWheel>")
            self._owner.unbind_all("<Button-1>")       # remove our bind_all click-outside guard
        except tk.TclError:
            pass
        if self._on_close:
            self._on_close(self)
        self.destroy()


def _is_dark(root) -> bool:
    try:
        return ttk.Style(root).lookup("TFrame", "background") == theme.DARK["bg"]
    except tk.TclError:
        return False


class PhaseBar(ttk.Frame):
    """The phase-button bar. `run` = {"label","command"} (the pink master); `phases` = list of
    {"label","run","buttons":[{"label","kind","command"}]}. Action-running buttons are appended to
    `run_buttons` so the App greys them while a worker is in flight."""

    def __init__(self, parent, run, phases, run_buttons, **kw):
        super().__init__(parent, **kw)
        self._phases = phases
        self._chevrons: list = []
        self._open: _Dropdown | None = None
        self.bind("<Destroy>", lambda e: self.close() if e.widget is self else None)  # rebuild -> drop popup
        self.grid_rowconfigure(0, minsize=_HEADER_H)    # tall phase headers
        self.grid_rowconfigure(1, minsize=_CHEVRON_H)   # chevrons ~2/3 of the header height

        col = 0
        if run and run.get("command"):                 # the pink master (omitted in the slim designer)
            b_run = ttk.Button(self, text=_wrap(run["label"], _BTN_WIDTH), width=_BTN_WIDTH, style="Run.TButton",
                               command=run["command"])
            b_run.grid(row=0, column=col, rowspan=2, sticky="nsew", padx=(2, 6), pady=2)
            run_buttons.append(b_run)
            col += 1

        for phase in phases:
            if col > 0:                                # ">" only between items, not before the first
                ttk.Label(self, text=">").grid(row=0, column=col, rowspan=2, padx=2)
                col += 1
            header = ttk.Button(self, text=_wrap(phase["label"], _BTN_WIDTH), width=_BTN_WIDTH, style="Phase.TButton",
                                command=phase.get("run"))
            header.grid(row=0, column=col, sticky="nsew", padx=1, pady=(2, 0))
            if phase.get("run"):
                run_buttons.append(header)
            chev = ttk.Button(self, text=_CHEVRON, style="Chevron.TButton")
            chev.grid(row=1, column=col, sticky="nsew", padx=1, pady=(0, 2))
            chev.configure(command=lambda p=phase, c=chev: self._toggle(p, c))
            self._chevrons.append(chev)
            col += 1

    def _toggle(self, phase, chevron):
        reopen_same = self._open is not None and self._open_chevron is chevron
        self.close()
        if reopen_same:
            return
        root = self.winfo_toplevel()
        self._open = _Dropdown(root, chevron, phase.get("buttons", []),
                               ignore=self._chevrons, on_close=self._cleared)
        self._open_chevron = chevron

    def _cleared(self, dd):
        if self._open is dd:
            self._open = None
            self._open_chevron = None

    def close(self):
        if self._open is not None:
            self._open.close()
        self._open = None
        self._open_chevron = None

    # the chevron currently bound to the open dropdown (None when closed)
    _open_chevron = None
