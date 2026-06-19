"""Phase 200 - Documents Fill Out (the I/O-List populator).

Four sub-phase buttons (210 Script Type, 220 Index, 230 Diag Cabinet, 240 Diag Bit) each fill one
column; the phase header runs the full populate (all columns + DiagnosisBlocks). Halts the pipeline
if any entry is unresolved.
"""
from __future__ import annotations

from pipeline3.phase import Phase, SubPhase, PhaseResult, Button, KIND_ACTION, KIND_OPEN
from pipeline3.registry import register
from pipeline3.domain.iolist_diag import populate as pop
from pipeline3.domain.iolist_diag.report import summary


def _fill(ctx, write):
    res = pop.populate(ctx.params, write=write, out_dir=ctx.out_root, emit=ctx.emit)
    ctx.populated_path = res.output_path
    return res


def run(ctx) -> PhaseResult:
    res = _fill(ctx, None)
    s = summary(res.counts)
    if res.halt:
        s += (f"  -> HALT: {res.unresolved} unresolved entr(y/ies) - fill them in the SOURCE "
              f"I/O List (see the '_UnresolvedIndex' sheet) and re-run.")
    return PhaseResult(ok=not res.halt, halt=res.halt,
                       artifacts={"populated_iolist": res.output_path}, summary=s)


SUB_PHASES = [
    SubPhase(210, "fill_script_type", "pb_fill_script_type", lambda ctx: _fill(ctx, {"script_type"})),
    SubPhase(220, "fill_index", "pb_fill_index", lambda ctx: _fill(ctx, {"index"})),
    SubPhase(230, "fill_diag_cabinet", "pb_fill_diag_cabinet", lambda ctx: _fill(ctx, {"diag_cabinet"})),
    SubPhase(240, "fill_diag_bit", "pb_fill_diag_bit", lambda ctx: _fill(ctx, {"diag_bit"})),
]

BUTTONS = [
    Button("pb_fill_script_type", KIND_ACTION, 210, "210"),
    Button("pb_fill_index", KIND_ACTION, 220, "220"),
    Button("pb_fill_diag_cabinet", KIND_ACTION, 230, "230"),
    Button("pb_fill_diag_bit", KIND_ACTION, 240, "240"),
    Button("pb_open_iolist", KIND_OPEN, 250, "open:io_list"),
    Button("pb_open_fill_config", KIND_OPEN, None, "open:fill_config"),
    Button("pb_open_signal_types", KIND_OPEN, None, "open:signal_types"),
]

register(Phase(
    number=200, key="fill", name_key="ph_fill", run=run, requires=(),
    buttons=BUTTONS, sub_phases=SUB_PHASES,
    inputs=("io_list.path", "signal_types.csv", "object_families.csv"),
    outputs=("populated_iolist",),
))
