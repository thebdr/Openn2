"""gui_common.py - widgets shared by gui.py and gui_designer.py.

- the vertical, cascading validation buttons (Run all on top, a small down-arrow between steps);
- the File (project manager) + Language menu bar;
- the Archive popup (date/time checkbox + project-name textbox);
- render_validation_log(): replay a validation log into a viewer (section banners + aligned lines
  with a leading cell link and an optional trailing other-workbook link).
"""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk

from pipeline2.core import i18n, validation


# --------------------------------------------------------------------------- #
# validation cascade (vertical, left, "Run all" on top, arrows between steps) #
# --------------------------------------------------------------------------- #
def build_validation_cascade(parent, run_all, steps, on_run, run_buttons) -> ttk.Frame:
    """parent: container; run_all: (label, phase_set); steps: [(label, phase_set), ...];
    on_run(phase_set): callback; run_buttons: list to append the buttons to (busy-disable).
    Returns the frame (caller packs it on the left)."""
    frame = ttk.Frame(parent, padding=(8, 8))

    b = ttk.Button(frame, text=run_all[0], width=22, command=lambda: on_run(run_all[1]))
    b.pack(side="top", fill="x")
    run_buttons.append(b)

    for label, phase_set in steps:
        ttk.Label(frame, text="↓", anchor="center").pack(side="top", fill="x")   # down arrow
        sb = ttk.Button(frame, text=label, width=22, command=lambda p=phase_set: on_run(p))
        sb.pack(side="top", fill="x")
        run_buttons.append(sb)
    return frame


# --------------------------------------------------------------------------- #
# menu bar (File: project manager + copy-inputs; Language: EN/IT)             #
# --------------------------------------------------------------------------- #
def build_menubar(root, callbacks: dict, lang_var: tk.StringVar, copy_inputs_var: tk.BooleanVar):
    """Build (or rebuild) the menu bar. callbacks: new/open/save/save_as/archive/quit/
    set_language/toggle_copy_inputs. Returns the menubar (already attached to root)."""
    lang = lang_var.get()
    mb = tk.Menu(root)

    filem = tk.Menu(mb, tearoff=0)
    filem.add_command(label=i18n.tr("menu_new", lang), command=callbacks["new"])
    filem.add_command(label=i18n.tr("menu_open", lang), command=callbacks["open"])
    filem.add_command(label=i18n.tr("menu_save", lang), command=callbacks["save"])
    filem.add_command(label=i18n.tr("menu_save_as", lang), command=callbacks["save_as"])
    filem.add_separator()
    filem.add_checkbutton(label=i18n.tr("menu_copy_inputs", lang), variable=copy_inputs_var,
                          command=callbacks.get("toggle_copy_inputs"))
    filem.add_separator()
    filem.add_command(label=i18n.tr("menu_archive", lang), command=callbacks["archive"])
    if callbacks.get("quit"):
        filem.add_separator()
        filem.add_command(label=i18n.tr("menu_quit", lang), command=callbacks["quit"])
    mb.add_cascade(label=i18n.tr("menu_file", lang), menu=filem)

    langm = tk.Menu(mb, tearoff=0)
    for code, name in (("en", "English"), ("it", "Italiano")):
        langm.add_radiobutton(label=name, value=code, variable=lang_var,
                              command=callbacks["set_language"])
    mb.add_cascade(label=i18n.tr("menu_language", lang), menu=langm)

    root.config(menu=mb)
    return mb


# --------------------------------------------------------------------------- #
# archive popup                                                               #
# --------------------------------------------------------------------------- #
def ask_archive(parent, default_name: str, lang: str = "en") -> dict | None:
    """Modal: an archive-name textbox (pre-filled with `default_name`) + an 'append date/time'
    checkbox. Returns {"name": str, "add_datetime": bool} or None if cancelled."""
    dlg = tk.Toplevel(parent)
    dlg.title(i18n.tr("archive_title", lang))
    dlg.transient(parent)
    dlg.resizable(False, False)
    result = {"value": None}

    frm = ttk.Frame(dlg, padding=12)
    frm.pack(fill="both", expand=True)
    ttk.Label(frm, text=i18n.tr("archive_name", lang)).grid(row=0, column=0, sticky="w", pady=(0, 4))
    name_var = tk.StringVar(value=default_name)
    entry = ttk.Entry(frm, textvariable=name_var, width=40)
    entry.grid(row=0, column=1, sticky="we", padx=(8, 0), pady=(0, 4))
    dt_var = tk.BooleanVar(value=False)
    ttk.Checkbutton(frm, text=i18n.tr("archive_add_datetime", lang), variable=dt_var).grid(
        row=1, column=0, columnspan=2, sticky="w", pady=(2, 10))

    btns = ttk.Frame(frm)
    btns.grid(row=2, column=0, columnspan=2, sticky="e")

    def ok():
        result["value"] = {"name": name_var.get().strip() or default_name,
                           "add_datetime": dt_var.get()}
        dlg.destroy()

    def cancel():
        dlg.destroy()

    ttk.Button(btns, text=i18n.tr("btn_ok", lang), command=ok).pack(side="right")
    ttk.Button(btns, text=i18n.tr("btn_cancel", lang), command=cancel).pack(side="right", padx=(0, 6))
    frm.columnconfigure(1, weight=1)
    entry.focus_set()
    entry.select_range(0, "end")
    dlg.bind("<Return>", lambda e: ok())
    dlg.bind("<Escape>", lambda e: cancel())
    dlg.grab_set()
    parent.wait_window(dlg)
    return result["value"]


# --------------------------------------------------------------------------- #
# render a validation log into a (level, text, link) emitter                  #
# --------------------------------------------------------------------------- #
def render_validation_log(section_fn, line_fn, log, full_print: bool = True, ce_path: str = "") -> None:
    """Replay a validation log into a viewer via two callbacks:
      section_fn(title)                                  -> a phase banner;
      line_fn(level, location, body, link1, link2)       -> every other line.
    The aligned caller-vs-other comparison table, the full_print/grey filter and the link building all live
    in validation.render_lines - this is just the dispatch, shared by gui.py and gui_designer.py.
    link1 is the leading cell (clickable); link2 is the other workbook on a not-PASS partial."""
    for rec in validation.render_lines(log, full_print=full_print, ce_path=ce_path):
        if rec.kind == "phase":
            section_fn(rec.title)
        else:
            line_fn(rec.level, rec.location, rec.body, rec.link1, rec.link2)
