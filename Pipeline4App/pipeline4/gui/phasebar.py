"""The phase-button bar: a 2-row grid of composite phase buttons driven by the phase REGISTRY
(`gui/phases.py`, transcribed from the operator oracle `ButtonsLayout.xlsx`).

Layout (the reviewed icon/layout redesign over the PL3 oracle): the pink "Run Pipeline" master on the
left (spans both rows), then a row of EQUAL-WIDTH phase HEADERS (row 0, each RUNS its phase) separated
by ➡, with a grey ▾ CHEVRON strip beneath each (row 1, ~60% of its former height) that opens an
anchored, click-away `_Dropdown` of that phase's SUB-BUTTONS. Each header is a composite `_PhaseButton`
(classic tk widgets - themed ttk buttons can't take the ButtonsLayout fill colours):

    [icon]  <number>     <- 24 px registry icon (assets/icons/phase_icons.yaml) + the phase number
    <description>        <- the localized phase name, NARROW font (theme.narrow_family), max 2 lines

The dropdown's width MATCHES the header/chevron column above it; its buttons are coloured by kind
(action=white · open=light-blue · special=orange · disabled=grey) and a thin divider separates the
action steps from the open/special steps. When the dropdown would extend past the APP WINDOW's bottom
edge it clamps there and gains a scrollbar (mouse-wheel scrolls it while open).

The bar is UI-only: the App supplies `on_phase(number, title)` (run a whole phase / Run-all) and
`resolve_sub(phase, sub) -> command|None` (a sub-button's command; None = greyed/disabled).
"""
from __future__ import annotations

import sys
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

from pipeline4.core import i18n
from pipeline4.gui import icons, phases, theme

_CHEVRON = "▾"           # opens a phase's sub-button dropdown (small glyph - the strip is ~60% height)
_SEP = "➡"               # between phase headers
_BTN_PX = 136            # header / run column width in px (EQUAL width; the dropdown matches it)
_ICON_PX = 24            # the registry icons' rendered size (72 px assets at subsample 3)
_WRAP = 13               # sub-button label word-wrap width (chars)
_CHEV_FONT_SIZE = 8      # the ▾ glyph size - measured: 17px vs the old ▼ row's 28px = 61% (the -40% spec)


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


def _shade(color: str, factor: float = 0.92) -> str:
    """`color` (#rrggbb) darkened by `factor` - the composite buttons' hover feedback."""
    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    return f"#{int(r * factor):02x}{int(g * factor):02x}{int(b * factor):02x}"


def _button(parent, label, kind, command, *, bold=False, width=1, pady=6, padx=6, font_size=None):
    """A coloured classic tk.Button for the chevron strip + the dropdown sub-buttons (disabled when
    command is None). `width` is in chars but the callers stretch with sticky/fill, so 1 = "size to
    the column"."""
    fill_kind = kind if command is not None else "disabled"
    weight = "bold" if bold else "normal"
    size = font_size if font_size is not None else theme.MONO_FONT[1]
    b = tk.Button(
        parent, text=label, command=command, width=width,
        bg=theme.BUTTON_FILLS[fill_kind], fg=theme.BUTTON_FG[fill_kind],
        activebackground=theme.BUTTON_FILLS[fill_kind], activeforeground=theme.BUTTON_FG[fill_kind],
        relief="flat", borderwidth=0, padx=padx, pady=pady, cursor="hand2",
        font=(theme.MONO_FONT[0], size, weight),
    )
    if command is None:
        b.configure(state="disabled", cursor="arrow")
    return b


class _PhaseButton(tk.Frame):
    """A composite phase button: `[icon] <number>` over a 2-line narrow-font description, centered,
    on a ButtonsLayout fill. Classic widgets with manual click/hover/disabled handling (a plain
    tk.Button cannot lay out an image+text line over a second text line)."""

    def __init__(self, parent, *, kind, number, desc, icon, command,
                 num_font, desc_font, width_px, height_px):
        self._kind = kind
        self._command = command
        self._enabled = True
        fill = theme.BUTTON_FILLS[kind]
        fg = theme.BUTTON_FG[kind]
        super().__init__(parent, bg=fill, width=width_px, height=height_px, cursor="hand2")
        self.pack_propagate(False)

        self._parts = []                      # every child that mirrors the fill/cursor state
        top = None
        if icon is not None or number:
            top = tk.Frame(self, bg=fill)
            top.pack(side="top", expand=True, pady=(3, 0))
            self._parts.append(top)
            if icon is not None:
                lbl = tk.Label(top, image=icon, bg=fill, borderwidth=0)
                lbl.pack(side="left", padx=(0, 6 if number else 0))
                self._parts.append(lbl)
            if number:
                lbl = tk.Label(top, text=number, bg=fill, fg=fg, font=num_font, borderwidth=0)
                lbl.pack(side="left")
                self._parts.append(lbl)
        self._desc = tk.Label(self, text=desc, bg=fill, fg=fg, font=desc_font,
                              wraplength=width_px - 14, justify="center", borderwidth=0)
        self._desc.pack(side="top", expand=True, pady=(0, 3))
        self._parts.append(self._desc)

        for w in (self, *self._parts):
            w.bind("<Button-1>", self._click)
            w.bind("<Enter>", lambda e: self._hover(True))
            w.bind("<Leave>", lambda e: self._hover(False))

    def _click(self, _event=None):
        if self._enabled and self._command is not None:
            self._command()

    def _hover(self, on: bool):
        if not self._enabled:
            return
        fill = _shade(theme.BUTTON_FILLS[self._kind]) if on else theme.BUTTON_FILLS[self._kind]
        self._apply_fill(fill, theme.BUTTON_FG[self._kind], "hand2")

    def _apply_fill(self, fill: str, fg: str, cursor: str):
        self.configure(bg=fill, cursor=cursor)
        for w in self._parts:
            w.configure(bg=fill, cursor=cursor)
            if isinstance(w, tk.Label) and not w.cget("image"):
                w.configure(fg=fg)

    def set_enabled(self, enabled: bool) -> None:
        """Greyed while a run is in flight (mirrors a disabled tk.Button's fill/fg/cursor)."""
        self._enabled = enabled
        kind = self._kind if enabled else "disabled"
        self._apply_fill(theme.BUTTON_FILLS[kind], theme.BUTTON_FG[kind],
                         "hand2" if enabled else "arrow")

    def set_desc(self, text: str) -> None:
        """Re-label the description in place (the language toggle; the number/icon are static)."""
        self._desc.configure(text=text)


def _remove_global_binding(widget, sequence, funcid) -> None:
    """Remove ONLY `funcid` from the global 'all' bindtag for `sequence`. Tk's `unbind_all` takes no
    funcid - it wipes EVERY handler on the tag - so this filters the bound script down to the others
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
        import os
        import win32gui
        import win32process
        fg = win32gui.GetForegroundWindow()
        return bool(fg) and win32process.GetWindowThreadProcessId(fg)[1] != os.getpid()
    except Exception:  # noqa: BLE001
        return False


class _Dropdown(tk.Toplevel):
    """An anchored, click-away-to-close popup of a phase's sub-buttons. Its width matches the anchor
    (the chevron/header column above it); a thin divider separates the action steps from open/special.
    Its HEIGHT clamps at the app window's bottom edge - past that it scrolls (scrollbar + mouse wheel)."""

    def __init__(self, root, anchor, specs, ignore, on_close, mode="dark"):
        super().__init__(root)
        self.withdraw()                       # build off-screen, show only once positioned
        self._owner = root                    # never name this `_root` - it shadows a tk method
        self._ignore = ignore
        self._on_close = on_close
        self._closed = False
        self._poll = None
        self._btn_funcid = None               # the bind_all("<Button-1>") id (removed precisely on close)
        self._wheel_funcid = None             # the bind_all("<MouseWheel>") id, set only when scrollable
        self._canvas = None
        self.overrideredirect(True)
        try:
            self.attributes("-topmost", True)
        except tk.TclError:
            pass

        border = tk.Frame(self, bg=theme.BUTTON_FILLS["chevron"], padx=1, pady=1)
        border.pack(fill="both", expand=True)
        canvas = tk.Canvas(border, highlightthickness=0, borderwidth=0,
                           bg=theme.bg_for(mode), yscrollincrement=16)
        inner = tk.Frame(canvas, bg=theme.bg_for(mode))
        prev_section = None
        for spec in specs:                    # spec = (label, kind, command, section)
            label, kind, command, section = spec
            if prev_section is not None and section != prev_section:
                tk.Frame(inner, bg=theme.BUTTON_FILLS["chevron"], height=1).pack(fill="x", pady=2)
            b = _button(inner, _wrap(label, _WRAP), kind, command, padx=3)
            b.pack(fill="x", pady=(0, 1))
            prev_section = section

        self.update_idletasks()
        x = anchor.winfo_rootx()
        y = anchor.winfo_rooty() + anchor.winfo_height()
        # MATCH the dropdown width to the column above it (the chevron == the header column width).
        width = max(anchor.winfo_width(), 1)
        content_h = inner.winfo_reqheight()
        # Clamp at the APP WINDOW's bottom edge (the user's spec); below a sane minimum, still show
        # a usable strip. Taller content scrolls.
        avail = max(80, root.winfo_rooty() + root.winfo_height() - y - 6)
        scrollable = content_h > avail
        shown_h = min(content_h, avail)
        sb_w = 0
        if scrollable:
            vsb = ttk.Scrollbar(border, orient="vertical", command=canvas.yview)
            canvas.configure(yscrollcommand=vsb.set)
            vsb.pack(side="right", fill="y")
            sb_w = max(vsb.winfo_reqwidth(), 10)
        canvas.pack(side="left", fill="both", expand=True)
        inner_w = width - 2 - sb_w
        canvas.create_window((0, 0), window=inner, anchor="nw", width=inner_w)
        canvas.configure(width=inner_w, height=shown_h, scrollregion=(0, 0, inner_w, content_h))
        self._canvas = canvas

        x = max(0, min(x, self.winfo_screenwidth() - width - 4))
        self.geometry(f"{width}x{shown_h + 2}+{x}+{y}")
        self.deiconify()
        self.lift()

        self.bind("<Escape>", lambda e: self.close())
        self._btn_funcid = root.bind_all("<Button-1>", self._maybe_close, "+")
        if scrollable:
            self._wheel_funcid = root.bind_all("<MouseWheel>", self._on_wheel, "+")
        # also close when the app loses focus to another application (alt-tab / clicking another app),
        # which the click-away handler can't see - POLL the OS foreground window. Keep the id so a fast
        # close can cancel it.
        self._poll = root.after(120, self._blur_poll)

    def _on_wheel(self, event):
        if self._closed or self._canvas is None:
            return
        try:
            self._canvas.yview_scroll(-1 * (event.delta // 120) * 2, "units")
        except tk.TclError:
            pass

    def _blur_poll(self):
        if self._closed:
            return
        if _foreground_is_other_app():
            self.close()
            return
        self._poll = self._owner.after(150, self._blur_poll)

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
        _remove_global_binding(self._owner, "<MouseWheel>", self._wheel_funcid)
        try:
            if self._poll is not None:
                self._owner.after_cancel(self._poll)
        except tk.TclError:
            pass
        if self._on_close:
            self._on_close(self)
        self.destroy()


def _section(sub) -> str:
    """The dropdown section a sub-button belongs to (action steps vs the open/special tail) - the divider
    boundary, mirroring the oracle's `↓` cascade -> `—` divider transition."""
    return "action" if sub.kind == "action" else "aux"


class PhaseBar(tk.Frame):
    """The 2-row, equal-width phase-button bar (composite header + chevron strip) driven by the registry.
    `on_phase(number, title)` runs a whole phase (or Run-all for number 0); `resolve_sub(phase, sub)`
    returns a sub-button's command (None = disabled/greyed)."""

    def __init__(self, parent, on_phase, resolve_sub, lang="en", mode="dark"):
        super().__init__(parent, bg=theme.phasebar_bg(mode))
        self._on_phase = on_phase
        self._resolve_sub = resolve_sub
        self._lang = i18n.normalize(lang)
        self._mode = mode
        self._buttons: list = []              # the run master + phase headers (greyed during a run)
        self._headers: list = []              # (_PhaseButton, phase) pairs to re-translate on a lang toggle
        self._chevrons: list = []
        self._separators: list = []           # tk.Label ➡ separators between phase columns
        self._spacers: list = []              # tk.Frame placeholders for phases with no sub-buttons
        self._open: _Dropdown | None = None
        self._open_chevron = None
        self.bind("<Destroy>", lambda e: self.close() if e.widget is self else None)

        # the icon set (held on self - a garbage-collected PhotoImage blanks its label) + the fonts
        self._icons, icon_warnings = icons.load_phase_icons(self)
        for line in icon_warnings:
            print(f"[phasebar] {line}", file=sys.stderr)
        narrow = theme.narrow_family(self)
        self._num_font = (narrow, 12, "bold")
        self._desc_font = (narrow, 9)
        desc_ls = tkfont.Font(root=self, family=narrow, size=9).metrics("linespace")
        num_ls = tkfont.Font(root=self, family=narrow, size=12, weight="bold").metrics("linespace")
        btn_h = max(_ICON_PX, num_ls) + 2 * desc_ls + 12      # icon/number line + a 2-line description

        col = 0
        phase_seen = 0
        for phase in phases.PHASES:
            key = "run" if phase.number == 0 else str(phase.number)
            icon = self._icons.get(key)
            if phase.number == 0:             # the pink Run master, spanning both rows on the left
                run = _PhaseButton(
                    self, kind="run", number="", desc=i18n.tr(phase.name_key, self._lang), icon=icon,
                    command=lambda n=0, k=phase.name_key: on_phase(n, i18n.tr(k, self._lang)),
                    num_font=self._num_font, desc_font=self._desc_font,
                    width_px=_BTN_PX, height_px=btn_h)
                run.grid(row=0, column=col, rowspan=2, sticky="nsew", padx=(2, 8), pady=3)
                self._buttons.append(run)
                self._headers.append((run, phase))
                col += 1
                continue
            if phase_seen > 0:                # a ➡ only BETWEEN phases (not after Run / before the first)
                sep = tk.Label(self, text=_SEP, bg=theme.phasebar_bg(self._mode),
                               fg=theme.fg_for(self._mode), font=(theme.MONO_FONT[0], 13))
                sep.grid(row=0, column=col, padx=1)
                self._separators.append(sep)
                col += 1
            header = _PhaseButton(
                self, kind="phase", number=str(phase.number), desc=i18n.tr(phase.name_key, self._lang),
                icon=icon,
                command=lambda n=phase.number, k=phase.name_key: on_phase(n, i18n.tr(k, self._lang)),
                num_font=self._num_font, desc_font=self._desc_font,
                width_px=_BTN_PX, height_px=btn_h)
            header.grid(row=0, column=col, sticky="nsew", padx=1, pady=(3, 0))
            self._buttons.append(header)
            self._headers.append((header, phase))
            if phase.subs:
                chev = _button(self, _CHEVRON, "chevron", None, pady=0, font_size=_CHEV_FONT_SIZE)
                chev.configure(command=lambda p=phase, c=chev: self._toggle(p, c),
                               state="normal", cursor="hand2")
                chev.grid(row=1, column=col, sticky="nsew", padx=1, pady=(0, 3))
                self._chevrons.append(chev)
            else:                             # display-only phase (no sub-steps) - a thin spacer row
                sp = tk.Frame(self, bg=theme.phasebar_bg(self._mode), height=4)
                sp.grid(row=1, column=col, sticky="nsew")
                self._spacers.append(sp)
            phase_seen += 1
            col += 1

    def _toggle(self, phase, chevron):
        reopen_same = self._open is not None and self._open_chevron is chevron
        self.close()
        if reopen_same:
            return
        specs = []
        for sub in phase.subs:
            command = self._resolve_sub(phase, sub)
            label = f"{sub.number}  {i18n.tr(sub.label_key, self._lang)}"
            specs.append((label, sub.kind, command, _section(sub)))
        # wrap each command so firing it also closes the dropdown
        specs = [(label, kind, (None if cmd is None else (lambda c=cmd: self._fire_through(c))), section)
                 for (label, kind, cmd, section) in specs]
        root = self.winfo_toplevel()
        self._open = _Dropdown(root, chevron, specs, ignore=self._chevrons, on_close=self._cleared,
                               mode=self._mode)
        self._open_chevron = chevron

    def _fire_through(self, command):
        self.close()
        command()

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
        for button in self._buttons:
            button.set_enabled(enabled)
        state = "normal" if enabled else "disabled"
        for chevron in self._chevrons:
            chevron.configure(state=state, cursor="hand2" if enabled else "arrow")
        if not enabled:
            self.close()

    def set_lang(self, lang: str) -> None:
        """Re-translate the bar in place for a new language (the run master + the phase headers; the chevron
        dropdowns re-resolve from `self._lang` each time they open)."""
        self._lang = i18n.normalize(lang)
        self.close()                          # a stale-language dropdown must not linger
        for button, phase in self._headers:
            button.set_desc(i18n.tr(phase.name_key, self._lang))

    def set_theme(self, mode: str) -> None:
        """Re-theme the bar for a light/dark mode switch: update the frame background, the ➡ separators,
        and the spacer frames. Phase buttons keep their oracle fills (they work in both modes). Closes any
        open dropdown so it reopens fresh-themed on the next chevron click."""
        self._mode = mode
        pb_bg = theme.phasebar_bg(mode)
        pb_fg = theme.fg_for(mode)
        self.configure(bg=pb_bg)
        for sep in self._separators:
            sep.configure(bg=pb_bg, fg=pb_fg)
        for sp in self._spacers:
            sp.configure(bg=pb_bg)
        self.close()
