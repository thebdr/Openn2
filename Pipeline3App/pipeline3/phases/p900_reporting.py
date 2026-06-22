"""Phase 900 - Reporting.

910 Generate Pipeline Coverage Report: trace each staged signal's life from validation (100) through
staging (300) to every downstream output (interfaces 400, I/O tags 510, data blocks 520, diagnosis
610/620, hardware 700, software 800) and flag ORPHAN (a signal that lands in no output) / UNPLACED (a
generator that references a generated-DB member 520 never creates). Writes
Reports/io_project_coverage_report.{csv,txt} (documentation - NOT a Open2App import surface). See
domain/coverage.py. Validates Pipeline3's OWN outputs, so it needs only the staged database (300).

920 Generate TIA Portal Project Coverage Report is DEFERRED (pending a real TIA project export) - a
disabled stub. 930 Open Reports Folder is GUI-era (M11). Depends on Staging (300).
"""
from __future__ import annotations

from pipeline3.phase import Phase, SubPhase, PhaseResult, Button, KIND_ACTION, KIND_OPEN, KIND_DISABLED
from pipeline3.registry import register
from pipeline3.domain import coverage


def _coverage(ctx) -> PhaseResult:
    res = coverage.generate(ctx.rows, ctx.out_root)
    st = res["stats"]
    ctx.emit(f"coverage: {st['rows']} staged row(s) - {st['kinds']['signal']} signal(s); "
             f"ORPHAN {st['orphans']}, UNPLACED {st['unplaced']} -> {res['txt_path']}")
    if st["missing"]:
        ctx.emit("  NOTE outputs not on disk (run those phases for a complete trace): "
                 + ", ".join(st["missing"]))
    for o in res["orphans"]:
        ctx.emit(f"  ORPHAN   {o['source']} {o['script_type']} {o['FLD']} [{o['address']}]")
    for u in res["unplaced"]:
        ctx.emit(f"  UNPLACED [{u['db']}] \"{u['member']}\"  <- {u['referenced_by']}")
    return PhaseResult(ok=True, artifacts={"coverage_report": res["txt_path"]},
                       summary=f"{st['orphans']} orphan(s), {st['unplaced']} unplaced")


def run(ctx) -> PhaseResult:
    return _coverage(ctx)


SUB_PHASES = [
    SubPhase(910, "cov_pipeline", "pb_gen_cov_pipeline", _coverage),
    SubPhase(920, "cov_tia", "pb_gen_cov_tia", None),   # deferred - pending a real TIA project export
]

BUTTONS = [
    Button("pb_gen_cov_pipeline", KIND_ACTION, 910, "910"),
    Button("pb_gen_cov_tia", KIND_DISABLED, 920, "920"),
    Button("pb_open_reports", KIND_OPEN, 930, "open:coverage_report"),
]

register(Phase(
    number=900, key="reporting", name_key="ph_reporting", run=run, requires=(300,),
    buttons=BUTTONS, sub_phases=SUB_PHASES,
    inputs=("io_database", "io_tags_dir", "blocks_import_dir", "blocks_creation_dir",
            "diagnosis_dir", "interfaces_dir", "hardware_dir"),
    outputs=("coverage_report",),
))
