#!/usr/bin/env bash
# C-024 verification: the chain-reaction engine + the Tempemplator renderer - the renderer grammar
# (incl. the 3 shipped worked examples rendered for real, the table-loop column check, located
# errors), the engine lifecycle (compile validation, provenance spawn, append-per-match, the audit
# with outcomes, the Deferred/settle pair, the strict empty-hook no-op, every former raw exception a
# finding), the run-plan smokes (a configured project through the real run_staging + the halted
# path), the expr parser EOF + bad-regex pins, and the byte-parity oracle (the engine lands dark:
# parity proves an empty rule set changes nothing, and that the expr edits left the strict emitters
# byte-identical). Exit code = verdict.
set -e
cd "$(dirname "$0")/.."
PY=../.venv/Scripts/python.exe
"$PY" tests/unit/test_tempemplator.py
"$PY" tests/unit/test_chain_reactions.py
"$PY" tests/unit/test_siemens_main_handlers.py
"$PY" tests/unit/test_expr_adversarial.py
"$PY" scripts/parity_vs_pl4.py
