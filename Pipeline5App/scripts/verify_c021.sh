#!/usr/bin/env bash
# C-021's recorded verification command: the plugin-seam + descriptor + laws tests, then the
# PL4 byte-parity oracle. Exit code = the verdict (composes with zen-record-run).
set -e
cd "$(dirname "$0")/.."
PY=../.venv/Scripts/python.exe
"$PY" tests/unit/test_systems_contract.py
"$PY" tests/unit/test_system_siemens.py
"$PY" tests/unit/test_architecture_contracts.py
"$PY" scripts/parity_vs_pl4.py
