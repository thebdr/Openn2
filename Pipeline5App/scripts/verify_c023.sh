#!/usr/bin/env bash
# C-023 verification: the per-system GUI projection - the PhaseSet contract + Siemens registry pins,
# the HEADLESS real-data run of the whole run_plan, meta consumption + multi-system routing, the
# empty ratchet (laws L1-L5), and the PL4 byte-parity oracle. Exit code = verdict.
set -e
cd "$(dirname "$0")/.."
PY=../.venv/Scripts/python.exe
"$PY" tests/unit/test_gui_phase_model.py
"$PY" tests/unit/test_siemens_main_handlers.py
"$PY" tests/unit/test_project_manager.py
"$PY" tests/unit/test_architecture_contracts.py
"$PY" scripts/parity_vs_pl4.py
