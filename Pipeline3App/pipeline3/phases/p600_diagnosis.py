"""Phase 600 - Diagnosis Mapping.

610 Generate Diag List: DiagList_IO.csv (in-diagnosis signals) + DiagList_Logic.csv (rule-generated)
into diagnosis_dir (ProjectDocumentation - documentation, NOT the Open2App BuilderData surface).
620 Generate Diag Software Blocks: fill the OPC diagnosis SCL template -> blocks_import_dir/
Diagnostic_for_OPC.scl (the Open2App import surface). See domain/diagnosis.py. 630/640 (Open Diag
Data / Diag Config folder) are GUI-era (M11). Depends on Staging (300); the rule cabinet mapping +
the SCL cabinets need the DiagnosisBlocks sheet (from Fill 230/240) in the I/O List.
"""
from __future__ import annotations

from pipeline3.phase import Phase, SubPhase, PhaseResult, Button, KIND_ACTION, KIND_OPEN
from pipeline3.registry import register
from pipeline3.core import config
from pipeline3.domain import diagnosis


def _diag_list(ctx) -> PhaseResult:
    res = diagnosis.generate_diag_list(ctx.rows, ctx.out_root, ctx.io_list_path())
    ctx.emit(f"diag list: {res['io_count']} DiagList_IO + {res['logic_count']} DiagList_Logic "
             f"-> {res['dir']}")
    return PhaseResult(ok=True, artifacts={"diagnosis_dir": res["dir"]},
                       summary=f"{res['io_count']} IO + {res['logic_count']} logic diag row(s)")


def _diag_blocks(ctx) -> PhaseResult:
    res = diagnosis.generate_diag_scl(ctx.rows, ctx.out_root, ctx.io_list_path())
    for w in res["warnings"]:
        ctx.emit(f"  WARN {w}")
    ctx.emit(f"diag SCL: {res['entries']} channel(s) across {res['cabinets']} cabinet(s) "
             f"-> {res['path'] or res['dir']}")
    return PhaseResult(ok=not res["warnings"], artifacts={"blocks_import_dir": res["dir"]},
                       summary=f"OPC SCL ({res['entries']} channels, {res['cabinets']} cabinets)")


def run(ctx) -> PhaseResult:
    r1 = _diag_list(ctx)
    r2 = _diag_blocks(ctx)
    artifacts = dict(r1.artifacts)
    artifacts.update(r2.artifacts)
    return PhaseResult(ok=r1.ok and r2.ok, artifacts=artifacts,
                       summary=f"{r1.summary}; {r2.summary}")


SUB_PHASES = [
    SubPhase(610, "gen_diag_list", "pb_gen_diag_list", _diag_list),
    SubPhase(620, "gen_diag_swblocks", "pb_gen_diag_swblocks", _diag_blocks),
]

BUTTONS = [
    Button("pb_gen_diag_list", KIND_ACTION, 610, "610"),
    Button("pb_gen_diag_swblocks", KIND_ACTION, 620, "620"),
    Button("pb_open_diag_data", KIND_OPEN, 630, "open:diagnosis_dir"),
    Button("pb_open_diag_config", KIND_OPEN, 640, "open:diag_config"),
]

register(Phase(
    number=600, key="diagnosis", name_key="ph_diagnosis", run=run, requires=(300,),
    buttons=BUTTONS, sub_phases=SUB_PHASES,
    inputs=("io_database", "diagnosis_columns.csv", "diagnosis_logic_rules.csv", "diag_scl_template"),
    outputs=("diagnosis_dir", "blocks_import_dir"),
))
