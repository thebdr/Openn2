#!/usr/bin/env bash
# C-051 verification: a document on another drive than the project is imported, never a failed import. It proves:
#   - project_manager._inside: a file inside, the root itself, a sibling sharing the name's prefix, the parent - and on
#     Windows another drive, a UNC share, the root in another case - answers, never raises;
#   - import_documents with the I/O List on a drive the machine lacks reports it `missing` (issue #2's
#     'Paths don't have the same drive' before), and a real file under another drive spelling (`\\?\C:\...`) is
#     copied into input_documents/ and rewritten relative; the existing import / stale-refresh cases still hold;
#   - the PL4 parity oracle is 0 diffs.
# Exit code = verdict. PY may be set to another interpreter (a git worktree has no ../.venv of its own).
set -e
cd "$(dirname "$0")/.."
PY="${PY:-../.venv/Scripts/python.exe}"
"$PY" tests/unit/test_project_manager.py
"$PY" scripts/parity_vs_pl4.py
