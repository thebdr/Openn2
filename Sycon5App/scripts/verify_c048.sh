#!/usr/bin/env bash
# C-048 verification: the user's SYCON.net functions recorded and replayed (auto addressing, the two exports). It
# proves, without SYCON.net:
#   - the process-data export read back on the FVZ production reference (the controller and the devices by display
#     name, the station name inside it) and the export kinds the menu offers;
#   - the shipped nWid/UpdateCardV5.bat (the remembered card, the renamed nxd) against a fake driver folder.
# The recorder and the replays are verified on the VM: the recordings under spike/references/recordings and the
# exports of every FVT build (`verify_exports` in the reports).
# Exit code = verdict. PY may be set to another interpreter (a git worktree has no ../.venv of its own).
set -e
cd "$(dirname "$0")/.."
PY="${PY:-../.venv/Scripts/python.exe}"
"$PY" -m pytest -q tests/test_exports.py tests/test_update_card_bat.py tests/test_refute_c048.py
