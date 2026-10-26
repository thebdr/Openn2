#!/usr/bin/env bash
# C-047 verification: the PL5 handoff built into a SYCON.net project and verified by read-back. It proves, without
# SYCON.net:
#   - the handoff tables read (`#!openn` header, the kinds, the optional columns, the parameters' notation);
#   - the build plan: the stations grouped by type and model in natural order, the clone-safe structures, the
#     parameter oracles (potential group records, DAP records), the verification's PASS / FAIL / NOTE rules;
#   - the canvas layout applied to the saved XML (rows by FLD, the symbolic names, the bus lines);
#   - PL5's export of the handoff (one card per PROFINET network, the fixed modules, the symbolic-name rules).
# The builds themselves are verified on the VM: the four FVT projects and the timed fast sorter, their reports
# under spike/references/FVT_tests (823 PASS / 0 FAIL, 107 / 0, 265 / 0, 528 / 0).
# Exit code = verdict. PY may be set to another interpreter (a git worktree has no ../.venv of its own).
set -e
cd "$(dirname "$0")/.."
PY="${PY:-../.venv/Scripts/python.exe}"
PY="$(cd "$(dirname "$PY")" && pwd)/$(basename "$PY")"
"$PY" -m pytest -q tests/test_handoff.py tests/test_build_plan.py tests/test_canvas.py tests/test_refute_c047.py tests/test_update_mode.py
(cd ../Pipeline5App && "$PY" -m pytest -q tests/unit/test_sycon_handoff.py)
