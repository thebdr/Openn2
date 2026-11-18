#!/usr/bin/env bash
# C-046 verification: the SYCON.net GUI driver, its read-back oracle and the structure laws. It proves, without
# SYCON.net:
#   - the read-back parser on the saved fixtures (E2E rounds 1-3): names, IPs, device ids, slots, submodules, records,
#     the controller's device list, the canvas boxes and bus lines;
#   - the five structure laws (one dependency direction, the oracle apart, the GUI sealed, one facade, the tests
#     never drive) and the ratchet;
#   - the package imports without the driver's packages (the driver loaded lazily).
# The driver itself is verified on the VM (scripts/e2e_driver_round3.py, the FVT builds of C-047).
# Exit code = verdict. PY may be set to another interpreter (a git worktree has no ../.venv of its own).
set -e
cd "$(dirname "$0")/.."
PY="${PY:-../.venv/Scripts/python.exe}"
"$PY" -m pytest -q tests/test_readback.py tests/test_architecture_contracts.py tests/test_package_import.py tests/test_refute_c046.py tests/test_drawing_lines.py tests/test_grid_anchor.py
