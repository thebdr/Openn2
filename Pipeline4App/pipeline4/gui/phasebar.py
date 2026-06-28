"""The phase-button bar: a 2-row grid of classic `tk.Button`s (so they can take the ButtonsLayout fill
colours - themed ttk buttons can't take a custom background).

Built from the phase REGISTRY (`gui/phases.py`) - the single source of the phase order/labels (no
re-encoding). Layout (mirrors PL3): the pink "Run Pipeline" master on the left (spans both rows), then a
row of phase HEADERS (row 0, each RUNS its phase) separated by ➡, with a grey ▼ CHEVRON beneath each
(row 1) that opens an anchored, scrollable, click-away dropdown of that phase's SUB-STEPS (M4).

PL4 NOTE: a phase handler is monolithic (it runs all of the phase's sub-phases - e.g. 620 SCL still needs
stage -> 520 -> build), so a sub-step button RUNS ITS PARENT PHASE, like the header. The dropdown is the
visual MAP of what a phase does; independent per-sub-phase runs wait on the engine. `set_enabled(False)`
greys every button (the worker-thread busy guard) and closes any open dropdown.
"""
from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk

from pipeline4.gui import phases, theme

_CHEVRON = "▼"           # opens a phase's sub-step dropdown
_SEP = "➡"               # between phase headers
_HEADER_WRAP = 14        # header label word-wrap width (chars)
_SUB_WRAP = 22           # dropdown sub-step label word-wrap width (chars)


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


def _button(parent, label, kind, command, *, bold=False):
    """A coloured classic tk.Button for the phase bar / dropdown (disabled when command is None)."""
    weight = "bold" if bold else "normal"
    b = tk.Button(
        parent, text=label, command=command,
        bg=theme.BUTTON_FILLS[kind], fg=theme.BUTTON_FG[kind],
        activebackground=theme.BUTTON_FILLS[kind], activeforeground=theme.BUTTON_FG[kind],
        relief="flat", borderwidth=0, padx=10, pady=6, cursor="hand2",
        font=(theme.MONO_FONT[0], theme.MONO_FONT[1], weight),
    )
    if command is None:
        b.configure(state="disabled", cursor="arrow")
    return b


def _remove_global_binding(widget, sequence, funcid) -> None:
    """Remove ONLY `funcid` from the global 'all' bindtag for `sequence`. Tk's `unbind_all` takes no
    funcid - it wipes EVERY handler on the tag - so use it directly would clobber any other global
    `<Button-1>` binding the app adds later. This filters the bound script down to the other handlers
    (mirrors what `Misc.unbind(seq, funcid)` does, but against the 'all' tag)."""
    if not funcid:
        return
    try:
        existing = widget.tk.call("bind", "all", sequence).split("\n")
        remaining = [line for line in existing if funcid not in line]
        widget.tk.call("bind", "all", sequence, "\n".join(remaining))
        widget.deletecommand(funcid)
    except tk.TclError:
        pass


def _foreground_is_other_app() -> bool:
    """True when the OS foreground window belongs to a DIFFERENT process - i.e. the app lost focus
    (alt-tab / clicking another application). Best-effort: returns False without pywin32 / off Windows,
    so the popup just keeps its click-away behaviour there."""
    try:
        import win32gui
        import win32process
        fg = win32gui.GetForegroundWindow()
        return bool(fg) and win32process.GetWindowThreadProcessId(fg)[1] != os.getpid()
    except Exception:  # noqa: BLE001
        return False


class _Dropdown(tk.Toplevel):
    """An anchored, click-away-to-close popup of a phase's sub-step buttons (a port of PL3's `_Dropdown`,
    trimmed: PL4 sub-lists are <=4 short items, so no scroll canvas is needed)."""

    def __init__(self, root, anchor, specs, ignore, on_close):
        super().__init__(root)
        self.withdraw()                       # build off-screen, show only once positioned
        self._owner = root                    # never name this `_root` - it shadows a tk method
        self._ignore = ignore
        self._on_close = on_close
        self._closed = False
        self._poll = None
        self._btn_funcid = None               # the bind_all("<Button-1>") id (removed precisely on close)
        self.overrideredirect(True)
        try:
            self.attributes("-topmost", True)
        except tk.TclError:
            pass

        border = tk.Frame(self, bg=theme.BUTTON_FILLS["chevron"], padx=1, pady=1)
        border.pack(fill="both", expand=True)
        inner = tk.Frame(border, bg=theme.DARK_BG)
        inner.pack(fill="both", expand=True)
        for i, (label, command) in enumerate(specs):
            b = _button(inner, _wrap(label, _SUB_WRAP), "action",
                        command=(lambda c=command: self._fire(c)))
            b.pack(fill="x", pady=(0 if i == 0 else 1, 0))

        self.update_idletasks()
        x = anchor.winfo_rootx()
        y = anchor.winfo_rooty() + anchor.winfo_height()
        x = max(0, min(x, self.winfo_screenwidth() - self.winfo_reqwidth() - 4))
        self.geometry(f"+{x}+{y}")
        self.deiconify()
        self.lift()

        self.bind("<Escape>", lambda e: self.close())
        self._btn_funcid = root.bind_all("<Button-1>", self._maybe_close, "+")
        # also close when the app loses focus to another application (alt-tab / clicking another app),
        # which the click-away handler can't see - POLL the OS foreground window (an overrideredirect
        # topmost popup doesn't get a reliable <Deactivate>). Keep the id so a fast close can cancel it.
        self._poll = root.after(120, self._blur_poll)

    def _blur_poll(self):
        if self._closed:
            return
        if _foreground_is_other_app():
            self.close()
            return
        self._poll = self._owner.after(150, self._blur_poll)

    def _fire(self, command):
        self.close()
        if command:
            command()

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
        _remove_global_binding(self._owner, "<Button-1>", self._btn_funcid)
        try:
            if self._poll is not None:
                self._owner.after_cancel(self._poll)
        except tk.TclError:
            pass
        if self._on_close:
            self._on_close(self)
        self.destroy()


class PhaseBar(tk.Frame):
    """The 2-row phase-button bar (header + chevron), driven by the registry. `on_click(number, label)`
    runs a phase (a sub-step runs its parent phase)."""

    def __init__(self, parent, on_click):
        super().__init__(parent, bg=theme.DARK_BG)
        self._on_click = on_click
        self._buttons: list = []              # the run master + phase headers (greyed during a run)
        self._chevrons: list = []
        self._open: _Dropdown | None = None
        self._open_chevron = None
        self.bind("<Destroy>", lambda e: self.close() if e.widget is self else None)

        col = 0
        phase_seen = 0
        for phase in phases.PHASES:
            if phase.number == 0:             # the pink Run master, spanning both rows on the left
                run = _button(self, _wrap(phase.title, _HEADER_WRAP), "run",
                              lambda n=0, lbl=phase.title: on_click(n, lbl), bold=True)
                run.grid(row=0, column=col, rowspan=2, sticky="nsew", padx=(2, 8), pady=3)
                self._buttons.append(run)
                col += 1
                continue
            if phase_seen > 0:                # a ➡ only BETWEEN phases (not after Run / before the first)
                ttk.Label(self, text=_SEP, background=theme.DARK_BG, foreground=theme.DARK_FG,
                          font=(theme.MONO_FONT[0], 13)).grid(row=0, column=col, padx=1)
                col += 1
            header = _button(self, _wrap(f"{phase.number}  {phase.title}", _HEADER_WRAP), "phase",
                             lambda n=phase.number, lbl=phase.title: on_click(n, lbl), bold=True)
            header.grid(row=0, column=col, sticky="nsew", padx=1, pady=(3, 0))
            self._buttons.append(header)
            if phase.subs:
                chev = _button(self, _CHEVRON, "chevron", None)
                chev.configure(command=lambda p=phase, c=chev: self._toggle(p, c),
                               state="normal", cursor="hand2")
                chev.grid(row=1, column=col, sticky="nsew", padx=1, pady=(0, 3))
                self._chevrons.append(chev)
            else:                             # display-only phase (no sub-steps) - a thin spacer row
                tk.Frame(self, bg=theme.DARK_BG, height=4).grid(row=1, column=col, sticky="nsew")
            phase_seen += 1
            col += 1

    def _toggle(self, phase, chevron):
        reopen_same = self._open is not None and self._open_chevron is chevron
        self.close()
        if reopen_same:
            return
        specs = [(f"{num}  {lbl}", lambda n=phase.number, plbl=phase.title: self._on_click(n, plbl))
                 for (num, lbl) in phase.subs]
        root = self.winfo_toplevel()
        self._open = _Dropdown(root, chevron, specs, ignore=self._chevrons, on_close=self._cleared)
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

    def set_enabled(self, enabled: bool) -> None:
        """Enable/disable every phase button (greyed while a run is in flight) + close any open dropdown."""
        state = "normal" if enabled else "disabled"
        for button in self._buttons:
            button.configure(state=state)
        for chevron in self._chevrons:
            chevron.configure(state=state)
        if not enabled:
            self.close()
