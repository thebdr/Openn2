"""The in-app guide (UI_REFRESH_PLAN I): a Help window over `docs/guide/*.md` + `index.yaml`, an
F1-able help-id registry, and the shared tooltip.

Content is Markdown files shipped NEXT TO THE SOURCE (the app ships its code - "read the source" is
always a valid final answer, so guide links use `src://relative/path` to open the shipped file, plus
`guide://section` cross-links and normal `https://`). The renderer covers the practical subset the
guide uses - #/##/### headings, **bold**, `code`, ``` fenced blocks, "- " bullets, [links](target) -
via a PURE `parse_markdown` (tested) rendered into a tk.Text with tags. No new dependency.

A section id WITHOUT a .md renders the missing-section page: "no instructions provided yet" + a link
to the source (the user's spec) - `missing_sections()` lists these as the authoring TODO
(scripts/list_guide_stubs.py prints it).

    attach(widget, "section-id")     # F1 on/inside the widget opens that section
    help_id_of(widget)               # the nearest attached ancestor's section id
    open_section(parent, "id")       # open/raise the Help window at a section
    add_tooltip(widget, "text")      # hover tooltip (adds an 'F1 - guide' hint when attached)
"""
from __future__ import annotations

import os
import re
import tkinter as tk
from tkinter import ttk

from pipeline5.gui import theme

# .../pipeline5/gui/guide_window.py -> up 3 -> the Pipeline5App root (docs/ lives there, like assets/).
APP_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GUIDE_DIR = os.path.join(APP_ROOT, "docs", "guide")

_HELP_ATTR = "_pl4_help_id"
_open_window = None                    # the singleton HelpWindow (re-raised, never duplicated)


# --- the Tk-free content half ---------------------------------------------------------------------- #
def load_index() -> list:
    """[(section_id, title)] from index.yaml, in display order; [] when the file is absent/broken."""
    path = os.path.join(GUIDE_DIR, "index.yaml")
    if not os.path.exists(path):
        return []
    try:
        from ruamel.yaml import YAML
        with open(path, encoding="utf-8") as handle:
            data = YAML(typ="safe").load(handle) or {}
        out = []
        for row in data.get("sections") or []:
            if isinstance(row, dict) and row.get("id"):
                out.append((str(row["id"]), str(row.get("title") or row["id"])))
        return out
    except Exception:  # noqa: BLE001 - a broken TOC must not take help down
        return []


def section_path(section_id: str) -> str:
    return os.path.join(GUIDE_DIR, f"{section_id}.md")


def has_section(section_id: str) -> bool:
    return os.path.exists(section_path(section_id))


def missing_sections() -> list:
    """The index rows without a .md yet - the visible authoring TODO."""
    return [sid for sid, _t in load_index() if not has_section(sid)]


_INLINE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)|\*\*([^*]+)\*\*|`([^`]+)`")


def _inline_spans(text: str) -> list:
    """One paragraph/bullet line -> [(style, text, link)] with style in '', 'bold', 'code', 'link'."""
    out, pos = [], 0
    for m in _INLINE.finditer(text):
        if m.start() > pos:
            out.append(("", text[pos:m.start()], ""))
        label, target, bold, code = m.groups()
        if label is not None:
            out.append(("link", label, target))
        elif bold is not None:
            out.append(("bold", bold, ""))
        else:
            out.append(("code", code, ""))
        pos = m.end()
    if pos < len(text):
        out.append(("", text[pos:], ""))
    return out


def parse_markdown(text: str) -> list:
    """The practical-subset parse: [(kind, payload)] where kind is h1/h2/h3 (payload=str),
    code_block (payload=str), bullet/p (payload=[(style, text, link)]), blank (payload='')."""
    ops, in_code, code_lines = [], False, []
    for raw in (text or "").splitlines():
        if raw.strip().startswith("```"):
            if in_code:
                ops.append(("code_block", "\n".join(code_lines)))
                code_lines = []
            in_code = not in_code
            continue
        if in_code:
            code_lines.append(raw)
            continue
        line = raw.rstrip()
        if not line.strip():
            ops.append(("blank", ""))
        elif line.startswith("### "):
            ops.append(("h3", line[4:]))
        elif line.startswith("## "):
            ops.append(("h2", line[3:]))
        elif line.startswith("# "):
            ops.append(("h1", line[2:]))
        elif line.lstrip().startswith("- "):
            ops.append(("bullet", _inline_spans(line.lstrip()[2:])))
        else:
            ops.append(("p", _inline_spans(line)))
    if in_code and code_lines:                     # an unclosed fence still renders
        ops.append(("code_block", "\n".join(code_lines)))
    return ops


def missing_page(section_id: str, source_hint: str = "") -> str:
    """The fallback page (the user's spec) - names the section, links the shipped source."""
    target = source_hint or "pipeline5"
    return (f"# {section_id}\n\n"
            f"No instructions provided for the requested functionality yet.\n\n"
            f"The application ships with its source code - see [{target}](src://{target}) "
            f"(you can modify and rebuild it), or add `docs/guide/{section_id}.md` to write "
            f"this section.\n")


# --- the help-id registry --------------------------------------------------------------------------- #
def attach(widget, section_id: str) -> None:
    """Mark `widget` (and thus everything inside it) as documented by `section_id` (F1 resolves it)."""
    setattr(widget, _HELP_ATTR, section_id)


def help_id_of(widget) -> str | None:
    """The nearest attached ancestor's section id (walking masters), or None."""
    w = widget
    while w is not None:
        sid = getattr(w, _HELP_ATTR, None)
        if sid:
            return sid
        w = getattr(w, "master", None)
    return None


# --- the shared tooltip ------------------------------------------------------------------------------ #
class Tooltip:
    """A hover tooltip (600 ms delay). When the widget sits under an attached help id, the text gains
    the 'F1 - guide' hint automatically."""

    def __init__(self, widget, text: str):
        self.widget, self.text = widget, text
        self._tip = None
        self._job = None
        widget.bind("<Enter>", self._schedule, "+")
        widget.bind("<Leave>", self._hide, "+")
        widget.bind("<Button>", self._hide, "+")

    def _schedule(self, _event=None):
        self._cancel()
        self._job = self.widget.after(600, self._show)

    def _cancel(self):
        if self._job:
            try:
                self.widget.after_cancel(self._job)
            except tk.TclError:
                pass
            self._job = None

    def _show(self):
        self._job = None
        if self._tip is not None or not self.widget.winfo_exists():
            return
        text = self.text
        if help_id_of(self.widget):
            text += "   (F1 - guide)"
        tip = tk.Toplevel(self.widget)
        tip.overrideredirect(True)
        try:
            tip.attributes("-topmost", True)
        except tk.TclError:
            pass
        label = tk.Label(tip, text=text, background="#333a40", foreground="#dfe6e9",
                         padx=6, pady=2, font=(theme.MONO_FONT[0], 9))
        label.pack()
        x = self.widget.winfo_rootx() + 8
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        tip.geometry(f"+{x}+{y}")
        self._tip = tip

    def _hide(self, _event=None):
        self._cancel()
        if self._tip is not None:
            try:
                self._tip.destroy()
            except tk.TclError:
                pass
            self._tip = None


def add_tooltip(widget, text: str) -> Tooltip:
    return Tooltip(widget, text)


# --- the Help window ---------------------------------------------------------------------------------- #
class HelpWindow(tk.Toplevel):
    def __init__(self, parent, mode: str = "dark"):
        super().__init__(parent)
        self.title("Pipeline5 - Guide")
        self.geometry("860x560")
        self._mode = mode

        panes = ttk.Panedwindow(self, orient="horizontal")
        panes.pack(fill="both", expand=True)
        left = ttk.Frame(panes)
        self.toc = ttk.Treeview(left, show="tree", selectmode="browse")
        self.toc.pack(side="left", fill="both", expand=True)
        self.toc.bind("<<TreeviewSelect>>", self._on_toc)
        panes.add(left, weight=1)

        right = ttk.Frame(panes)
        self.text = tk.Text(right, wrap="word", state="disabled", relief="flat", padx=14, pady=10,
                            background=theme.bg_for(mode), foreground=theme.fg_for(mode),
                            font=(theme.MONO_FONT[0], 10))
        vsb = ttk.Scrollbar(right, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)
        panes.add(right, weight=4)

        self._ids = {}                     # toc item -> section id
        for sid, title in load_index():
            item = self.toc.insert("", "end", text=title)
            self._ids[item] = sid
        self._configure_tags()
        self.bind("<Destroy>", self._on_destroy)

    def _configure_tags(self):
        base_family, base_size = theme.MONO_FONT[0], 10
        accent = "#74b9ff" if self._mode == "dark" else "#0055cc"
        code_bg = "#26292c" if self._mode == "dark" else "#eef0f2"
        self.text.tag_configure("h1", font=(base_family, base_size + 5, "bold"),
                                spacing1=6, spacing3=6)
        self.text.tag_configure("h2", font=(base_family, base_size + 2, "bold"),
                                spacing1=8, spacing3=3)
        self.text.tag_configure("h3", font=(base_family, base_size + 1, "bold"), spacing1=6)
        self.text.tag_configure("bold", font=(base_family, base_size, "bold"))
        self.text.tag_configure("code", background=code_bg)
        self.text.tag_configure("code_block", background=code_bg, lmargin1=18, lmargin2=18,
                                spacing1=4, spacing3=4)
        self.text.tag_configure("bullet", lmargin1=14, lmargin2=26)
        self.text.tag_configure("link", foreground=accent, underline=True)
        self.text.tag_bind("link", "<Enter>", lambda _e: self.text.configure(cursor="hand2"))
        self.text.tag_bind("link", "<Leave>", lambda _e: self.text.configure(cursor=""))

    def _on_toc(self, _event=None):
        sel = self.toc.selection()
        if sel and sel[0] in self._ids:
            self.show(self._ids[sel[0]])

    def _on_destroy(self, event):
        global _open_window
        if event.widget is self and _open_window is self:
            _open_window = None

    def show(self, section_id: str, source_hint: str = "") -> None:
        """Render `section_id` (or its missing-section page) and sync the TOC selection."""
        if has_section(section_id):
            with open(section_path(section_id), encoding="utf-8") as handle:
                content = handle.read()
        else:
            content = missing_page(section_id, source_hint)
        self._render(content)
        for item, sid in self._ids.items():        # keep the TOC in step (no event feedback loop:
            if sid == section_id:                  # selecting the already-selected row is a no-op)
                if self.toc.selection() != (item,):
                    self.toc.selection_set(item)
                self.toc.see(item)
                break
        self.lift()

    def _render(self, content: str) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        for tag in self.text.tag_names():
            if tag.startswith("link#"):
                self.text.tag_delete(tag)
        link_n = 0
        for kind, payload in parse_markdown(content):
            if kind in ("h1", "h2", "h3"):
                self.text.insert("end", payload + "\n", kind)
            elif kind == "code_block":
                self.text.insert("end", payload + "\n", "code_block")
            elif kind == "blank":
                self.text.insert("end", "\n")
            elif kind in ("p", "bullet"):
                if kind == "bullet":
                    self.text.insert("end", "• ", "bullet")
                for style, text, target in payload:
                    if style == "link":
                        link_n += 1
                        tag = f"link#{link_n}"
                        self.text.insert("end", text, ("link", tag, "bullet") if kind == "bullet"
                                         else ("link", tag))
                        self.text.tag_bind(tag, "<Button-1>",
                                           lambda _e, t=target: self._follow(t))
                    else:
                        tags = tuple(t for t in (style or None, "bullet" if kind == "bullet" else None)
                                     if t)
                        self.text.insert("end", text, tags)
                self.text.insert("end", "\n")
        self.text.configure(state="disabled")

    def _follow(self, target: str) -> None:
        """A link click: guide://section renders in place; src://rel opens the shipped file; http(s)
        opens the browser."""
        if target.startswith("guide://"):
            self.show(target[len("guide://"):])
        elif target.startswith("src://"):
            path = os.path.normpath(os.path.join(APP_ROOT, target[len("src://"):]))
            try:
                os.startfile(path)                 # the OS default app (editor / Explorer for a folder)
            except OSError:
                pass
        elif target.startswith(("http://", "https://")):
            import webbrowser
            webbrowser.open(target)


def open_section(parent, section_id: str, source_hint: str = "", mode: str | None = None) -> None:
    """Open (or raise) THE Help window at `section_id` - the F1 / '?' entry point."""
    global _open_window
    root = parent.winfo_toplevel() if hasattr(parent, "winfo_toplevel") else parent
    if _open_window is None or not _open_window.winfo_exists():
        _open_window = HelpWindow(root, mode=mode or "dark")
    _open_window.show(section_id, source_hint)
    _open_window.deiconify()
    _open_window.lift()
