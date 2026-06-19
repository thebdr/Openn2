"""Phase-100 validation builders (clean-room; Pipeline2 logic is reference for intent only).

Each builder takes the PipelineContext and returns a flat list[LogEntry] (no banner inside - the
phase-100 header runner frames each sub-phase). 110/120 read workbooks through the ONE shared
reader; 130/140/150 read the staged database (ctx.rows), and 130/140 also read the C&E workbook.
"""
from pipeline3.domain.validation.iolist import run_iolist
from pipeline3.domain.validation.matrix import run_ce_matrix
from pipeline3.domain.validation.crosscheck import run_xcheck_cem_iol, run_xcheck_iol_cem
from pipeline3.domain.validation.diagnosis import run_diagnosis

__all__ = ["run_iolist", "run_ce_matrix", "run_xcheck_cem_iol", "run_xcheck_iol_cem", "run_diagnosis"]
