#!/usr/bin/env bash
# C-024 verification: the chain-reaction engine + the Tempemplator renderer - the renderer grammar
# (incl. the 3 shipped worked examples rendered for real), the engine lifecycle (compile validation,
# provenance spawn, append-per-match, audit log, the strict empty-hook no-op), the expr parser EOF
# pin, and the byte-parity oracle (the engine lands dark). Exit code = verdict.
set -e
cd "$(dirname "$0")/.."
PY=../.venv/Scripts/python.exe
"$PY" tests/unit/test_tempemplator.py
"$PY" tests/unit/test_chain_reactions.py
"$PY" tests/unit/test_siemens_main_handlers.py
"$PY" tests/unit/test_expr_adversarial.py
"$PY" scripts/parity_vs_pl4.py
