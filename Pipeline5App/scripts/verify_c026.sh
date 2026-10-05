#!/usr/bin/env bash
# C-026 verification: the Files tab never drops an unsaved edit without asking. It proves, through the
# real FilesPanel on an off-screen Tk root (skipped without a display), messagebox.askyesno answering:
#   - every editing viewer (text pane, template mode, CSV grid, Object explorer) made dirty for real, then
#     every path that would replace or close it - a tree pick, the Text <-> Object toggle both ways, the
#     project-copy jump, the App's close - asks; No keeps the same widgets + edits, Yes replaces them;
#   - a light/dark switch reloads nothing (the same widgets, edits and view, re-themed);
#   - the text pane is clean again back at the saved text, and the load itself is not undoable;
#   - Revert and an open cell editor are the deliberate boundaries;
#   - headless: the Files tab reaches FileXY's widgets through public members only (dirty / set_theme).
# Exit code = verdict. PY may be set to another interpreter (a git worktree has no ../.venv of its own).
set -e
cd "$(dirname "$0")/.."
PY="${PY:-../.venv/Scripts/python.exe}"
"$PY" tests/unit/test_gui_files_discard.py
"$PY" tests/unit/test_filexy_shim.py
