"""phasebar.py - the horizontal phase-button bar + chevron dropdown popups.

A clean-room port of Pipeline2's `PhaseBar`/`_Dropdown` (UI-only: it renders a declarative phase spec
whose button `command`s are ready-to-call callables). The Pipeline3 change: the spec is **generated
from the phase registry** (`build_spec`, over `registry().presentation_order()` + i18n labels), never a
hand-written ordering. The buttons are classic `tk.Button`s coloured from `theme.tk_button_opts` (the
ButtonsLayout fills survive under sv-ttk, whose themed buttons are image-based); the chrome around
them is sv-ttk-themed.

Layout (assets/ButtonsLayout.xlsx): a row of phase headers separated by ">", with the pink "Run
Pipeline" master on the left. A header RUNS the whole phase; the grey chevron below opens an anchored,
scrollable dropdown of that phase's buttons - white "action" steps (˅ cascade between them), light-blue
"open", orange "special", greyed disabled - closing on Escape / a click outside / another chevron.
"""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk

from pipeline3.core import i18n
from pipeline3.gui import theme

# Between-button glyphs (assets/ButtonsLayout.xlsx). The flow arrows are heavy emoji codepoints drawn
# in EMOJI_FONT so they render BOLD (not a thin line); the chevron stays a GLYPH_FONT triangle.
_CHEVRON = "▼"           # opens a phase's dropdown (GLYPH_FONT)
_SEP = "➡"               # between phase headers (EMOJI_FONT, U+27A1)
_CASCADE = "⬇"           # between two ACTION steps (cascade; EMOJI_FONT, U+2B07)
_DIVIDER = "—"           # before an open / at a section boundary
_BTN_WIDTH = 12          # header / chevron / popup-button width (characters); labels word-wrap to fit
_HEADER_H = 60           # phase-header row height (~double a single-line button)
_CHEVRON_H = 20          # chevron row height (a short strip)
_GAP_H = 18              # inter-button gap height (↓ cascade or — divider)


def _wrap(text: str, width: int) -> str:
    """Greedily word-wrap `text` so each line is <= `width` chars (a longer word still gets its line)."""
    lines, cur = [], ""
    for word in str(text).split():
        if cur and len(cur) + 1 + len(word) > width:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}" if cur else word
    if cur:
        lines.append(cur)
    return "\n".join(lines)


def _button(parent, label, kind, dark, font, command, *, bold=False, width=_BTN_WIDTH):
    """A coloured classic tk.Button for the phase bar / dropdown."""
    b = tk.Button(parent, text=label, width=width, command=command,
                  **theme.tk_button_opts(kind, dark, font, bold=bold))
    if kind == "disabled" or command is None:
        b.configure(state="disabled")
    return b


# --------------------------------------------------------------------------------------------- #
# spec generated from the registry (the Pipeline3 change from Pipeline2's hand-written _phase_spec)
# --------------------------------------------------------------------------------------------- #
def build_spec(reg, lang, *, run_cb, phase_cb, button_cb, include_run=True, profile=None):
    """(run, phases) for PhaseBar from the registry's presentation order + i18n labels.
    `run_cb()` -> the pink master command (or None); `phase_cb(phase)` -> the header command;
    `button_cb(button, phase)` -> a dropdown Button's command (None = disabled). `include_run=False`
    (the designer profile) drops the pink master. `profile` filters the bar to that profile's
    PRESENTATION set (designer -> only ph100; None/'main' -> all phases)."""
    phases = []
    for ph in reg.presentation_order(profile):
        phases.append({
            "label": i18n.tr(ph.name_key, lang),
            "run": phase_cb(ph),
            "buttons": [{"label": i18n.tr(b.label_key, lang), "kind": b.kind,
                         "command": button_cb(b, ph)} for b in ph.buttons],
        })
    run = {"label": i18n.tr("pb_run_pipeline", lang), "command": run_cb() if include_run else None}
    return run, phases


# --------------------------------------------------------------------------------------------- #
# the dropdown popup
# --------------------------------------------------------------------------------------------- #
def _gap(parent, arrow: bool):
    """The inter-button gap: a `↓` cascade between two action steps, else a `—` divider."""
    g = ttk.Frame(parent, height=_GAP_H)
    g.pack_propagate(False)
    ttk.Label(g, text=_CASCADE if arrow else _DIVIDER, anchor="center",
              font=(theme.EMOJI_FONT, 12)).pack(fill="both", expand=True)
    g.pack(fill="x")


def _scrollable(parent, bg: str):
    outer = ttk.Frame(parent)
    canvas = tk.Canvas(outer, highlightthickness=0, background=bg)
    vs = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=vs.set)
    inner = ttk.Frame(canvas)
    win = canvas.create_window((0, 0), window=inner, anchor="nw")
    inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win, width=e.width))
    canvas.bind("<Enter>", lambda e: canvas.bind_all(
        "<MouseWheel>", lambda ev: canvas.yview_scroll(int(-ev.delta / 120), "units")))
    canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))
    return outer, canvas, vs, inner


def _foreground_is_other_app() -> bool:
    """True when the OS foreground window belongs to a DIFFERENT process - i.e. this app has lost focus
    (alt-tab / clicking another application). Best-effort: returns False without pywin32 / off Windows,
    so the popup just keeps its click-away behaviour there."""
    try:
        import os
        import win32gui
        import win32process
        fg = win32gui.GetForegroundWindow()
        return bool(fg) and win32process.GetWindowThreadProcessId(fg)[1] != os.getpid()
    except Exception:  # noqa: BLE001
        return False


class _Dropdown(tk.Toplevel):
    """An anchored, scrollable, click-away-to-close popup of a phase's buttons."""

    def __init__(self, root, anchor, buttons, ignore, on_close, *, dark, bg, font):
        super().__init__(root)
        self.withdraw()                       # build off-screen, show only once positioned
        self._owner = root                    # never name this `_root` - it shadows a tk method
        self._ignore = ignore
        self._on_close = on_close
        self._closed = False
        self._poll = None
        self.overrideredirect(True)
        try:
            self.attributes("-topmost", True)
        except tk.TclError:
            pass

        border = ttk.Frame(self, relief="solid", borderwidth=1)
        border.pack(fill="both", expand=True)
        outer, canvas, vs, inner = _scrollable(border, bg)

        prev_kind = None
        for spec in buttons:
            kind = spec.get("kind", "action")
            if prev_kind is not None:
                _gap(inner, arrow=(prev_kind == "action" and kind == "action"))
            b = _button(inner, _wrap(spec["label"], _BTN_WIDTH), kind, dark, font,
                        command=(lambda s=spec: self._fire(s)) if spec.get("command") else None)
            b.pack(fill="x")
            prev_kind = kind

        self.update_idletasks()
        x = anchor.winfo_rootx()
        y = anchor.winfo_rooty() + anchor.winfo_height()
        content_h = inner.winfo_reqheight()
        cap = max(140, (root.winfo_rooty() + root.winfo_height()) - y - 10)
        h = min(content_h, cap)
        canvas.configure(height=h, width=max(anchor.winfo_width(), inner.winfo_reqwidth()))
        if content_h > cap:
            vs.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        outer.pack(fill="both", expand=True)
        self.update_idletasks()
        x = max(0, min(x, self.winfo_screenwidth() - self.winfo_reqwidth() - 4))
        self.geometry(f"+{x}+{y}")
        self.deiconify()
        self.lift()

        self.bind("<Escape>", lambda e: self.close())
        root.bind_all("<Button-1>", self._maybe_close, "+")
        # also close when the app loses focus to another application (alt-tab / clicking another app),
        # which the click-away handler can't see. <Deactivate> proved unreliable for an overrideredirect
        # topmost popup, so POLL the OS foreground window instead (started once the open/lift settles).
        root.after(120, self._blur_poll)

    def _blur_poll(self):
        if self._closed:
            return
        if _foreground_is_other_app():          # another process owns the foreground -> the app lost focus
            self.close()
            return
        self._poll = self._owner.after(150, self._blur_poll)

    def _fire(self, spec):
        cmd = spec.get("command")
        self.close()
        if cmd:
            cmd()

    def _maybe_close(self, event):
        if self._closed or event.widget in self._ignore:
            return
        w = event.widget                      # keep open while the click is inside (ancestry, DPI-safe)
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
            self._owner.unbind_all("<Button-1>")
            if self._poll is not None:
                self._owner.after_cancel(self._poll)
        except tk.TclError:
            pass
        if self._on_close:
            self._on_close(self)
        self.destroy()


class PhaseBar(ttk.Frame):
    """The phase-button bar. `run` = {"label","command"} (the pink master, dropped when command is
    None); `phases` = list of {"label","run","buttons":[{"label","kind","command"}]}. Action-running
    buttons are appended to `run_buttons` so the App can grey them while a worker is in flight."""

    _open_chevron = None

    def __init__(self, parent, run, phases, run_buttons, *, dark=True, bg="#1c1c1c", font="Consolas", **kw):
        super().__init__(parent, **kw)
        self._phases = phases
        self._dark, self._bg, self._font = dark, bg, font
        self._chevrons: list = []
        self._open: _Dropdown | None = None
        self.bind("<Destroy>", lambda e: self.close() if e.widget is self else None)
        self.grid_rowconfigure(0, minsize=_HEADER_H)
        self.grid_rowconfigure(1, minsize=_CHEVRON_H)

        col = 0
        if run and run.get("command"):                 # the pink master (omitted in the slim designer)
            b_run = _button(self, _wrap(run["label"], _BTN_WIDTH), "run", dark, font,
                            command=run["command"], bold=True)
            b_run.grid(row=0, column=col, rowspan=2, sticky="nsew", padx=(2, 6), pady=2)
            run_buttons.append(b_run)
            col += 1

        for i, phase in enumerate(phases):
            if i > 0:                                # an arrow only BETWEEN phases (not after Run / before ph100)
                ttk.Label(self, text=_SEP, font=(theme.EMOJI_FONT, 16)).grid(
                    row=0, column=col, padx=2)      # row 0 only -> centered on the HEADER, not header+chevron
                col += 1
            header = _button(self, _wrap(phase["label"], _BTN_WIDTH), "phase", dark, font,
                             command=phase.get("run"), bold=True)
            header.grid(row=0, column=col, sticky="nsew", padx=1, pady=(2, 0))
            if phase.get("run"):
                run_buttons.append(header)
            chev = _button(self, _CHEVRON, "chevron", dark, font, command=None)
            chev.grid(row=1, column=col, sticky="nsew", padx=1, pady=(0, 2))
            # the command lambda needs `chev` to exist first, so it's set here - re-enable the button
            # too (creating it with command=None left it state="disabled", which ate every click).
            chev.configure(command=lambda p=phase, c=chev: self._toggle(p, c), state="normal")
            self._chevrons.append(chev)
            col += 1

    def _toggle(self, phase, chevron):
        reopen_same = self._open is not None and self._open_chevron is chevron
        self.close()
        if reopen_same:
            return
        root = self.winfo_toplevel()
        self._open = _Dropdown(root, chevron, phase.get("buttons", []),
                               ignore=self._chevrons, on_close=self._cleared,
                               dark=self._dark, bg=self._bg, font=self._font)
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
