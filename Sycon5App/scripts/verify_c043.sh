#!/usr/bin/env bash
# C-043 verification: the two generic-hardware project types of PL5 (validation + hardware generation alone). It
# proves, headless, from Pipeline5App:
#   - both types registered and named (EN / IT), phase sets 0 / 100 / 700, the Run-all plan (100, 700), the handlers
#     the shared chapters, the SYCON layout under the output root, the safety system untouched;
#   - each run_plan phase of each type on the fixture I/O List (sandboxed: Database / Output in temp folders) emits
#     a RSLT line and writes its tables; 110 alone writes no report;
#   - `mandatory_in` matched by id / taxonomy / `*`, the FAIL per empty mandatory column, the doubled PROFINET name;
#   - the SYCON handoff: one network per project, the second network INFO, in-network duplicates FAIL;
#   - the systems contract and the structure laws (L5: no system-id literal below the workbench);
#   - the refute tests of round 1 (tests/unit/test_refute_c043.py).
# Exit code = verdict. PY may be set to another interpreter (a git worktree has no ../.venv of its own).
set -e
cd "$(dirname "$0")/../../Pipeline5App"
PY="${PY:-../.venv/Scripts/python.exe}"
"$PY" -m pytest -q tests/unit/test_generic_hw_systems.py tests/unit/test_validation_standalone.py tests/unit/test_sycon_handoff.py tests/unit/test_systems_contract.py tests/unit/test_architecture_contracts.py tests/unit/test_refute_c043.py
"$PY" tests/unit/test_generic_hw_handlers.py
