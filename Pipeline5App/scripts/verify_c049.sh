#!/usr/bin/env bash
# C-049 verification: the TIA Portal version is a project setting. It proves:
#   - tia_version.py: the spellings (V20 / v20 / 20), the refusal of an unsupported version, blank or absent =
#     the builtin project_params.yaml's value (V20), the stamp replacing a template's own;
#   - the three SimaticML writers stamp it (the Global DBs, the tag tables, the FC XMLs from the templates) and an
#     explicit version wins; the workspace config carries `tia`;
#   - the safety System declares the New-project option, PL5's SUPPORTED list = OP5's Openness range
#     (OpennessSetup.cs), create_project writes the choice into the project's params and refuses an unoffered
#     value or an unknown option before anything is created;
#   - the structure laws still hold (the kernel dialog never names Siemens) and the PL4 parity oracle is 0 diffs
#     with the V20 stamps read as the reference's V18 (counted).
# Exit code = verdict. PY may be set to another interpreter (a git worktree has no ../.venv of its own).
set -e
cd "$(dirname "$0")/.."
PY="${PY:-../.venv/Scripts/python.exe}"
"$PY" tests/unit/test_tia_version.py
"$PY" tests/unit/test_plctags_xml.py
"$PY" tests/unit/test_datablock_generator.py
"$PY" tests/unit/test_software_blocks.py
"$PY" tests/unit/test_openn_header.py
"$PY" tests/unit/test_project_manager.py
"$PY" tests/unit/test_architecture_contracts.py
"$PY" scripts/parity_vs_pl4.py
