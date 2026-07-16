"""The colour-coded, link-aware log pane - a read-only `tk.Text` (v+h scrollbars) with one tag per
severity level. Two feeds:
- `append(level, message)` - a plain progress/summary line (PHASE banner, PASS summary).
- `append_records(records)` - the STRUCTURED log (`io.render.render_records`): each RenderRec carries the
  line text + the char spans of its `Sheet!Cell` cells (with their workbook `doc`). Each span becomes a
  clickable link (-> `on_link(doc, sheet, cell)` -> open the workbook in Excel at the cell); a treatable
  line's leading `[LEVEL]` tag is an errlink - LEFT-click -> `on_errjump(uid)` (the host opens the
  Findings tab at that row), right-click -> `on_errtreat(uid, level)` (the treat menu). Binding from the
  record (not by re-parsing text) is what makes the cross-workbook links work and can't race.
Inserts happen on the Tk main thread (the App drains its worker queue into here via `root.after`).
"""
from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

from pipeline5.gui import theme

_ACCENT_DARK = theme.LOG_COLORS["PHASE"][0]        # clickable-link colour in dark mode
_ACCENT = _ACCENT_DARK                            # module-level default (dark)
_TREATABLE = ("FAIL", "ERRR", "WARN")
_ALWAYS_SHOWN = ("PHASE", "SUBPHASE", "HEAD", "FAIL", "ERRR", "INFO", "RSLT")  # chrome + severity.UNHIDEABLE
# the render-mark style -> Text tag map (the cross-check comparison layers; see io/render.MarkSpan)
_MARK_TAGS = {"cmp": "cmp", "cmp_op_eq": "cmpopeq", "cmp_op_ne": "cmpopne", "cmp_diff": "cmpdiff"}
_CMP_DIFF_BG = {"dark": "#5b2b2b", "light": "#f6c9c9"}  # the =/= differing-chars highlight


class LogView(ttk.Frame):
    def __init__(self, parent, shown_levels=None, on_link=None, on_errtreat=None, on_errjump=None,
                 font_size=None, mode: str = "dark", **kw):
        super().__init__(parent, **kw)
        self.shown_levels = set(shown_levels) if shown_levels is not None else set(theme.LOG_COLORS)
        self.on_link = on_link                    # on_link(doc, sheet, cell)
        self.on_errtreat = on_errtreat            # on_errtreat(uid, level)
        self.on_errjump = on_errjump              # on_errjump(uid) - left-click [LEVEL] -> the Findings row
        self._links = 0
        self._errs = 0
        self._family = theme.MONO_FONT[0]         # the log font family + a live-resizable size (Font dropdown)
        self._size = int(font_size or theme.MONO_FONT[1])
        self._accent = _ACCENT_DARK               # updated by set_theme() on a mode toggle
        self._sink = None                         # an open text file when 'log to file' is ON (host-owned)

        self.text = tk.Text(self, wrap="none", relief="flat", borderwidth=0, state="disabled",
                            background=theme.DARK_BG, foreground=theme.DARK_FG,
                            insertbackground=theme.DARK_FG, font=(self._family, self._size), padx=8, pady=6)
        vs = ttk.Scrollbar(self, orient="vertical", command=self.text.yview)
        # the STABLE horizontal scrollbar (user spec): tk.Text maps its h-thumb against the longest
        # line currently VISIBLE, so the thumb resizes on every append/v-scroll. The adapter below
        # maps it against the longest line SEEN instead (_max_chars only ever grows; clear() resets).
        hs = ttk.Scrollbar(self, orient="horizontal", command=self._hsb_drag)
        self._hsb = hs
        self._max_chars = 0
        self._char_px = tkfont.Font(root=self, family=self._family, size=self._size).measure("0")
        self.text.configure(yscrollcommand=vs.set, xscrollcommand=self._hsb_update)
        self.text.grid(row=0, column=0, sticky="nsew")
        vs.grid(row=0, column=1, sticky="ns")
        hs.grid(row=1, column=0, sticky="ew")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        for level, (color, bold) in theme.LOG_COLORS.items():
            self.text.tag_configure(level, foreground=color, font=self._tag_font(level, bold))
        self._config_cmp_tags("dark")             # re-skinned below by set_theme(mode)
        self.text.tag_configure("errlink", underline=True)
        self.text.tag_bind("errlink", "<Enter>", lambda _e: self.text.configure(cursor="hand2"))
        self.text.tag_bind("errlink", "<Leave>", lambda _e: self.text.configure(cursor=""))
        self._apply_elide()                       # hide the not-shown levels (lines are inserted, then elided)
        self.set_theme(mode)                      # skin from the PERSISTED mode (the widget defaults are dark;
                                                  # a light-theme launch must not open a dark pane)

    # --- the stable horizontal scrollbar ---------------------------------------------------------- #
    def _track_width(self, line: str) -> None:
        if len(line) > self._max_chars:
            self._max_chars = len(line)

    def _stable_metrics(self) -> tuple:
        """(viewport_px, max_line_px, visible_longest_px, first_visible_fraction) - the fixed domain
        (the longest line seen) plus tk.Text's own visible-relative view state."""
        view_px = max(1, self.text.winfo_width() - 20)          # minus padding + a slack margin
        max_px = max(view_px, self._max_chars * self._char_px + 24)
        first, last = (float(v) for v in self.text.xview())
        frac = max(0.0, min(1.0, last - first))
        longest = view_px / frac if 0 < frac < 1 else view_px
        return view_px, max_px, longest, first

    def _hsb_update(self, _first, _last) -> None:
        """tk.Text's xscrollcommand -> the thumb re-mapped onto the stable longest-line-SEEN domain
        (so it never resizes as short lines append or the view scrolls vertically)."""
        view_px, max_px, longest, first_vis = self._stable_metrics()
        offset = first_vis * longest
        lo = max(0.0, min(1.0, offset / max_px))
        hi = max(lo, min(1.0, (offset + view_px) / max_px))
        self._hsb.set(lo, hi)

    def _hsb_drag(self, *args) -> None:
        """The scrollbar's command -> a stable-domain moveto converted back to tk.Text's
        visible-relative fraction (scroll units/pages pass straight through)."""
        if args and args[0] == "moveto":
            _view_px, max_px, longest, _f = self._stable_metrics()
            offset = float(args[1]) * max_px
            self.text.xview("moveto", offset / max(longest, 1.0))
        else:
            self.text.xview(*args)

    def append(self, level: str, message: str) -> None:
        """A plain (link-less) line - level-coloured. Inserted regardless of the shown set; a not-shown
        level's tag is ELIDED, so the Levels dropdown can show/hide it live."""
        level = (level or "INFO").upper()
        tag = level if level in theme.LOG_COLORS else "INFO"
        self._track_width(message)
        self.text.configure(state="normal")
        if level == "PHASE":
            self._phase_gap()
        self.text.insert("end", f"{message}\n", tag)
        self.text.see("end")
        self.text.configure(state="disabled")
        self._tee(f"[{level}] {message}")

    def _phase_gap(self, lines: int = 2) -> None:
        """Blank line(s) before a banner/title, so each section gets breathing room (2 before a main
        PHASE header, 1 before a smaller sub-phase header). Skipped at the very top of the log."""
        if self.text.compare("end-1c", ">", "1.0"):
            self.text.insert("end", "\n" * lines)

    def append_records(self, records) -> None:
        """Append structured records (`io.render.render_records`): sub-phase banners (the SMALLER
        SUBPHASE header - the main phase header arrives via `append('PHASE', …)`), level-coloured
        finding lines, clickable `Sheet!Cell` link spans, a treatable line's errlink, and the
        cross-check comparison marks (=== neutral / =/= diff-chars underlined)."""
        self.text.configure(state="normal")
        for rec in records:
            self._track_width(rec.text)
            if rec.kind == "banner":                    # a sub-phase section header (110/120/130/140)
                self._phase_gap(1)
                self.text.insert("end", rec.text + "\n", "SUBPHASE")
                self.text.insert("end", "-" * max(8, len(rec.text)) + "\n", "SUBPHASE")
                self._tee(rec.text)
                continue
            start = self.text.index("end-1c")
            tag = rec.level if rec.level in theme.LOG_COLORS else "INFO"
            self.text.insert("end", rec.text + "\n", tag)
            self._tag_errlink(start, rec)
            for span in rec.links:
                self._tag_link_span(start, span)
            for mark in getattr(rec, "marks", ()):
                if mark.style in _MARK_TAGS:
                    self.text.tag_add(_MARK_TAGS[mark.style],
                                      f"{start}+{mark.start}c", f"{start}+{mark.end}c")
            self._tee(rec.text)
        self.text.see("end")
        self.text.configure(state="disabled")

    def set_sink(self, sink) -> None:
        """Set (or clear, with None) the open text file the log is tee'd to while 'log to file' is ON. The
        host owns the file's lifecycle (open on toggle-on, close on toggle-off / window close)."""
        self._sink = sink

    def _tee(self, line: str) -> None:
        """Mirror one plain log line to the file sink (if any). Best-effort - a write failure never breaks
        the UI; the host can surface it."""
        if self._sink is None:
            return
        try:
            self._sink.write(line + "\n")
            self._sink.flush()
        except (OSError, ValueError):                   # closed/unwritable file - drop the tee silently
            pass

    def set_shown_levels(self, levels) -> None:
        """Set which log levels are visible (FAIL/ERROR/PHASE are always shown). Hides/shows in place via
        per-level elide - no re-render. The host persists the choice to app_config.yaml."""
        self.shown_levels = set(levels) | set(_ALWAYS_SHOWN)
        self._apply_elide()

    def _tag_font(self, level: str, bold: bool) -> tuple:
        """A level tag's font: the log family/size, bold per the palette - except SUBPHASE, which renders
        one point SMALLER (the sub-phase header sits visually under the bold main PHASE header)."""
        size = max(8, self._size - 1) if level == "SUBPHASE" else self._size
        return (self._family, size, "bold" if bold else "normal")

    def _config_cmp_tags(self, mode: str) -> None:
        """The cross-check comparison layers (configured AFTER the level tags so they take priority):
        the WHOLE comparison neutral grey, the === operator green, the =/= operator red, and the
        differing chars of a =/= on a red-ish BACKGROUND (the text above stays neutral)."""
        palette = theme.log_colors_for(mode)
        self.text.tag_configure("cmp", foreground=palette["SKIP"][0])
        self.text.tag_configure("cmpopeq", foreground=palette["PASS"][0])
        self.text.tag_configure("cmpopne", foreground=palette["FAIL"][0])
        self.text.tag_configure("cmpdiff", background=_CMP_DIFF_BG["dark" if mode == "dark" else "light"])

    def set_theme(self, mode: str) -> None:
        """Re-theme the log pane for a light/dark mode switch: background, foreground, all level tag
        colours, and the link accent colour. New content after this call uses the new palette; existing
        content keeps its old colours (the Text is not re-rendered)."""
        self._accent = theme.LOG_COLORS_LIGHT["PHASE"][0] if mode != "dark" else _ACCENT_DARK
        bg = theme.bg_for(mode)
        fg = theme.fg_for(mode)
        self.text.configure(background=bg, foreground=fg, insertbackground=fg)
        palette = theme.log_colors_for(mode)
        for level, (color, bold) in palette.items():
            self.text.tag_configure(level, foreground=color, font=self._tag_font(level, bold))
        self._config_cmp_tags(mode)

    def set_font_size(self, size: int) -> None:
        """Resize the log font live (the Text body + every level tag, preserving each tag's bold). The
        dynamic link/errlink tags carry no font, so they inherit the new size. The host persists the choice
        to app_config.yaml."""
        self._size = int(size)
        self.text.configure(font=(self._family, self._size))
        self._char_px = tkfont.Font(root=self, family=self._family, size=self._size).measure("0")
        for level, (_color, bold) in theme.LOG_COLORS.items():
            self.text.tag_configure(level, font=self._tag_font(level, bold))

    def _apply_elide(self) -> None:
        for level in theme.LOG_COLORS:
            self.text.tag_configure(level, elide=(level not in self.shown_levels and level not in _ALWAYS_SHOWN))

    def _tag_link_span(self, line_start, span) -> None:
        if not (self.on_link and span.doc and span.start < span.end):
            return                                # only a real-workbook (doc-bearing) span is a link
        s, e = f"{line_start}+{span.start}c", f"{line_start}+{span.end}c"
        token = self.text.get(s, e)
        sheet, cell = token.split("!", 1) if "!" in token else ("", "")
        tag = f"link{self._links}"
        self._links += 1
        self.text.tag_add(tag, s, e)
        self.text.tag_configure(tag, foreground=self._accent, underline=True)
        self.text.tag_bind(tag, "<Enter>", lambda _e: self.text.configure(cursor="hand2"))
        self.text.tag_bind(tag, "<Leave>", lambda _e: self.text.configure(cursor=""))
        self.text.tag_bind(tag, "<Button-1>",
                           lambda _e, d=span.doc, sh=sheet, c=cell: self.on_link(d, sh, c))

    def _tag_errlink(self, line_start, rec) -> None:
        """The leading `[LEVEL]` of a treatable line: LEFT-click jumps to the finding's row in the
        Findings tab (`on_errjump`); right-click opens the treat menu (`on_errtreat`)."""
        if rec.level not in _TREATABLE or not ((self.on_errtreat or self.on_errjump)
                                               and getattr(rec, "uid", "")):
            return
        end = f"{line_start}+{len(rec.level) + 2}c"            # "[" + level + "]"
        self.text.tag_add("errlink", line_start, end)
        tag = f"err{self._errs}"
        self._errs += 1
        self.text.tag_add(tag, line_start, end)
        if self.on_errtreat:
            self.text.tag_bind(tag, "<Button-3>", lambda e, u=rec.uid: self._err_menu(e, u))
        if self.on_errjump:
            self.text.tag_bind(tag, "<Button-1>", lambda _e, u=rec.uid: self.on_errjump(u))

    def _err_menu(self, event, uid: str) -> None:
        from pipeline5.core import finding_treatments as treatments
        menu = tk.Menu(self.text, tearoff=0)
        for level in treatments.TREATMENTS:                   # fail / error / warn / skip / ignore
            menu.add_command(label=f"Treat as {level.upper()}", command=lambda lv=level: self.on_errtreat(uid, lv),
                             # skip/ignore greyed for now (UI only) until the app reaches a stable version
                             state="disabled" if level in ("skip", "ignore") else "normal")
        menu.add_separator()
        menu.add_command(label="Clear treatment", command=lambda: self.on_errtreat(uid, ""))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def clear(self) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")
        self._links = 0
        self._errs = 0
        self._max_chars = 0                  # the ONLY reset of the stable h-scroll domain (user spec)
        self._hsb.set(0.0, 1.0)
