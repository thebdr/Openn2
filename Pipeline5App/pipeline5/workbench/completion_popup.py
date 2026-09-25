"""An autocomplete popup for a tk.Text - the ƒx builder's popup, generalised for the Files tab's
template mode (P-012). A borderless Listbox under the insert cursor: Down/Up move, Return/Tab accept
(replacing the stem), Escape or a click closes. While it is open it owns those four keys on the
text; closing hands them back (the widget's own bindings for them are untouched - it has none).
"""
from __future__ import annotations

import tkinter as tk

from pipeline5.workbench import theme

_KEYS = ("<Return>", "<Tab>", "<Down>", "<Up>")
NAVIGATION = ("Up", "Down", "Return", "Tab", "Escape")    # key releases that must not re-open it


class CompletionPopup:
    def __init__(self, text: tk.Text, mode: str = "dark", on_accept=None):
        self.text, self.mode, self.on_accept = text, mode, on_accept
        self.popup: tk.Toplevel | None = None
        self.listbox: tk.Listbox | None = None
        self._stem_start = "insert"
        text.bind("<Escape>", lambda _e: self.close(), "+")
        text.bind("<Button-1>", lambda _e: self.close(), "+")
        text.bind("<Destroy>", lambda e: self.close() if e.widget is text else None, "+")

    @property
    def is_open(self) -> bool:
        return self.popup is not None

    def show(self, candidates, stem_start: str) -> None:
        """Offer `candidates`; accepting one replaces the text from `stem_start` (a Tk index) to the
        insert mark. No candidates (or no visible cursor) = closed."""
        self.close()
        bbox = self.text.bbox("insert") if candidates else None
        if not bbox:
            return
        self._stem_start = stem_start
        x = self.text.winfo_rootx() + bbox[0]
        y = self.text.winfo_rooty() + bbox[1] + bbox[3]
        popup = tk.Toplevel(self.text)
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        listbox = tk.Listbox(popup, height=min(8, len(candidates)), font=theme.MONO_FONT,
                             background=theme.bg_for(self.mode), foreground=theme.fg_for(self.mode),
                             exportselection=False)
        for candidate in list(candidates)[:40]:
            listbox.insert("end", candidate)
        listbox.selection_set(0)
        listbox.pack()
        popup.geometry(f"+{x}+{y}")
        listbox.bind("<Double-1>", self.accept)
        self.popup, self.listbox = popup, listbox
        self.text.bind("<Return>", self.accept)
        self.text.bind("<Tab>", self.accept)
        self.text.bind("<Down>", lambda _e: self.move(1))
        self.text.bind("<Up>", lambda _e: self.move(-1))

    def accept(self, _event=None):
        if self.listbox is None:
            return None
        chosen = self.listbox.get(self.listbox.curselection() or 0)
        start = self._stem_start
        self.close()
        self.text.delete(start, "insert")
        self.text.insert("insert", chosen)
        if self.on_accept is not None:
            self.on_accept()
        return "break"

    def move(self, delta: int):
        listbox = self.listbox
        if listbox is None:
            return None
        current = (listbox.curselection() or (0,))[0]
        new = max(0, min(listbox.size() - 1, current + delta))
        listbox.selection_clear(0, "end")
        listbox.selection_set(new)
        listbox.see(new)
        return "break"

    def close(self) -> None:
        if self.popup is not None:
            try:
                self.popup.destroy()
            except tk.TclError:
                pass
            self.popup = self.listbox = None
        try:                                        # the text may be mid-teardown
            if self.text.winfo_exists():
                for sequence in _KEYS:
                    self.text.unbind(sequence)
        except tk.TclError:
            pass
