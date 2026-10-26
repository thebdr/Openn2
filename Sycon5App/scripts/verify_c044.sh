#!/usr/bin/env bash
# C-044 verification: the SYCON.net production folder - one project per cifX card, the canvas, BusField.csv. It
# proves, without SYCON.net:
#   - PL5's handoff: one folder per card (`HilscherIOCard<n>/SyconNetProjectInterface/`), the other cards' controllers
#     and stations INFO, the fixed modules, the symbolic-name rules, the manufacturer key, the coupler's connectors
#     mirrored, the DAP parameters row, the loader's refusals (Pipeline5App/tests/unit/test_sycon_handoff.py);
#   - the generic SYCON type writes it where its layout says (test_generic_hw_handlers.py, test_generic_hw_systems.py);
#   - the handoff's optional columns, the read-back's ids and rectangles, the canvas layout and its in-place apply,
#     the export reader, the shipped UpdateCardV5.bat (Sycon5App/tests);
#   - BusField.csv rows and header on a fake production folder, the refute tests of round 1 (tests/test_refute_c044.py).
# The builds themselves are verified on the VM (the sorter production folder, 823 PASS / 0 FAIL).
# Exit code = verdict. PY may be set to another interpreter (a git worktree has no ../.venv of its own).
set -e
cd "$(dirname "$0")/.."
PY="${PY:-../.venv/Scripts/python.exe}"
PY="$(cd "$(dirname "$PY")" && pwd)/$(basename "$PY")"
"$PY" -m pytest -q tests/test_handoff.py tests/test_readback.py tests/test_canvas.py tests/test_exports.py tests/test_update_card_bat.py tests/test_refute_c044.py
(cd ../Pipeline5App && "$PY" -m pytest -q tests/unit/test_sycon_handoff.py tests/unit/test_generic_hw_systems.py && "$PY" tests/unit/test_generic_hw_handlers.py)
