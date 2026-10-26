#!/usr/bin/env bash
# C-045 verification: the users' GUI - the workspace data and a log viewer. It proves, without SYCON.net (the window
# withdrawn, a fake workspace):
#   - `workspace.scan`: the cards and their state, the statuses, the command lines of the steps, the log levels;
#   - the GUI: the cards table, the buttons' enabling, the viewer's levels and filter, a real step through the runner
#     with its log file, a batch, a stop; the package imports without the driver's packages;
#   - the refute tests of round 1 (tests/test_refute_c045.py): odd card folders, unreadable reports, a project
#     folder gone, a step that cannot start, a step that writes nothing, a stop while idle, a workspace that vanished.
# The GUI on a real workspace is tried on the VM (Verify card streamed, coloured, the table refreshed).
# Exit code = verdict. PY may be set to another interpreter (a git worktree has no ../.venv of its own).
set -e
cd "$(dirname "$0")/.."
PY="${PY:-../.venv/Scripts/python.exe}"
"$PY" -m pytest -q tests/test_workspace.py tests/test_gui.py tests/test_package_import.py tests/test_refute_c045.py
