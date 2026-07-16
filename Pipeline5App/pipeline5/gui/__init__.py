"""The operator GUI (Tkinter). Launch: `python launch_gui.py`.

WHERE TO LOOK (_panel = a whole tab · _view = a reusable widget inside one):
  app_main.py            the window: worker thread, Run-all loop, tab wiring, open-targets
  phase_model.py         the Phase/Sub registry the phase bar renders (per-system at step 5)
  phasebar.py            the phase buttons + chevron sub-phase dropdowns
  chasebar.py            the Run-all progress strip
  log_view.py            the structured clickable log + severity filter
  excel_goto.py          jump to Sheet!Cell in Excel (COM) for the log's document links
  findings_panel.py / findings_view.py    the Findings tab / its grid
  files_panel.py / files_view.py          the config-driven Files tab / its tree+grid
  documents_panel.py     the input-documents tab (current/previous pickers)
  database_explorer.py   the SSOT explorer tab (lazy, stamped, chunked)
  database_query.py      its Tk-free in-memory SQLite mirror/query layer
  datagrid.py            the shared grid canvas (zebra, drag-resize, auto-fit)
  syntax_highlight.py    yaml/json highlighting        object_editor.py   Text <-> Object editor
  expr_builder.py        the fx expression dialog (lint, autocomplete, live preview)
  guide_window.py        the F1 in-app guide (markdown subset, guide://+src:// links)
  external_editor.py     open-externally helpers       filexy_shim.py     the FileXY dependency shim
  new_project.py · theme.py · fonts.py · icons.py · darktitle.py          dialog + chrome
"""
