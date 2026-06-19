"""Phase 300 - Documents Staging. Reads the (populated) I/O List into the single database and
writes IODatabase.csv. 310 stages (-> ctx.rows); 320 writes the CSV; the header runs both.
Depends on Fill (200) in the main profile; the designer profile stages the input doc read-only.
"""
from __future__ import annotations

from pipeline3.phase import Phase, SubPhase, PhaseResult, Button, KIND_ACTION, KIND_OPEN
from pipeline3.registry import register
from pipeline3.core import config
from pipeline3.domain import staging


def _stage(ctx) -> list:
    if ctx.rows is None:
        types = ctx.signal_types or config.load_signal_types()
        ctx.signal_types = types
        rows, warnings, matched, skipped = staging.load_io_list(ctx.params, types, ctx.io_list_path())
        ctx.rows = rows
        ctx.emit(f"staging: {len(rows)} row(s) from {', '.join(matched)}")
        for w in warnings:
            ctx.emit(f"  WARN {w}")
        for s in skipped:
            ctx.emit(f"  skipped sheet (no io_list.sheet match): {s}")
    return ctx.rows


def _stage_run(ctx) -> PhaseResult:
    rows = _stage(ctx)
    return PhaseResult(ok=True, summary=f"{len(rows)} rows staged")


def _gen_db(ctx) -> PhaseResult:
    rows = _stage(ctx)
    path = staging.write_io_database(rows, ctx.out_root)
    return PhaseResult(ok=True, artifacts={"io_database": path}, summary=f"IODatabase.csv ({len(rows)} rows)")


def run(ctx) -> PhaseResult:
    rows = _stage(ctx)
    path = staging.write_io_database(rows, ctx.out_root)
    return PhaseResult(ok=True, artifacts={"io_database": path},
                       summary=f"{len(rows)} rows staged -> IODatabase.csv")


SUB_PHASES = [
    SubPhase(310, "stage_iolist", "pb_stage_iolist", _stage_run),
    SubPhase(320, "gen_io_database", "pb_gen_io_database", _gen_db),
]

BUTTONS = [
    Button("pb_stage_iolist", KIND_ACTION, 310, "310"),
    Button("pb_gen_io_database", KIND_ACTION, 320, "320"),
    Button("pb_open_io_database", KIND_OPEN, 330, "open:io_database"),
]

register(Phase(
    number=300, key="staging", name_key="ph_staging", run=run, requires=(200,),
    buttons=BUTTONS, sub_phases=SUB_PHASES,
    inputs=("populated_iolist", "ce.path", "signal_types.csv", "column_map.csv"),
    outputs=("io_database",),
))
