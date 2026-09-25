#!/usr/bin/env bash
# C-025 verification: the template builder (the Files tab's template mode). It proves:
#   - the static lint against the renderer: every renderer error found on the renderer's own line,
#     the untaken branch, and in a rule's context the strict render's own verdicts;
#   - previews against REAL fires (rows, text + path, finding);
#   - the declared hook Databases against the fired ones (the Siemens smoke's pin);
#   - exact positions, the two-layer highlight, problem placement and completions, on the shipped
#     authoring manual;
#   - the real FilesPanel on an off-screen Tk root (skipped without a display): the template mode,
#     and the shipped config read-only in every viewer until copied.
# The MANUAL half - the user's pilot acceptance - is recorded in the evidence. Exit code = verdict.
set -e
cd "$(dirname "$0")/.."
PY=../.venv/Scripts/python.exe
"$PY" tests/unit/test_template_builder.py
"$PY" tests/unit/test_template_doc.py
"$PY" tests/unit/test_gui_template_mode.py
"$PY" tests/unit/test_siemens_main_handlers.py
