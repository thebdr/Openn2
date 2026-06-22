"""Composition root: run a single phase (with its prerequisites) or the whole pipeline.

The orchestrator topo-sorts on `requires` (NOT the phase-bar's left->right order) and memoizes via
ctx.completed, so "run any phase" from the bar transparently runs its prerequisites first. A phase
whose result.halt is True stops the run (e.g. phase 200 left unresolved entries).
"""
from __future__ import annotations

from pipeline3.phase import PhaseResult
from pipeline3.registry import registry as _global_registry


def run_phase(ctx, number: int, reg=None):
    """Run `number` and its transitive (in-profile) prerequisites, in dependency order.
    Returns the halting PhaseResult if any, else the last result run."""
    reg = reg or _global_registry()
    last = None
    for phase in reg.topo_order(target=number, profile=ctx.profile):
        if phase.number in ctx.completed:
            continue
        last = _run_one(ctx, phase)
        if last is not None and last.halt:
            return last
    return last


def run_all(ctx, reg=None):
    """Run the whole profile in dependency order. Stops early on a halting result."""
    reg = reg or _global_registry()
    last = None
    for phase in reg.topo_order(profile=ctx.profile):
        if phase.number in ctx.completed:
            continue
        last = _run_one(ctx, phase)
        if last is not None and last.halt:
            return last
    return last


def _run_one(ctx, phase):
    try:
        result = phase.run(ctx)
    except OSError as e:
        # a file write/access failure (e.g. an output locked open) is a clean ERROR that STOPS the
        # pipeline - not a raw traceback. The phase is left un-completed, so it retries on a re-run.
        path = getattr(e, "filename", "") or ""
        reason = e.strerror or str(e)
        ctx.emit(f"[ERROR] phase {phase.number} ({phase.key}): could not write file"
                 + (f" {path}" if path else "") + f" ({reason}); pipeline stopped")
        return PhaseResult(ok=False, halt=True, summary=f"file write failed: {path or reason}")
    ctx.absorb(result)
    ctx.completed.add(phase.number)
    if result is not None and result.halt:
        ctx.emit(f"HALT at phase {phase.number} ({phase.key}): {result.summary}")
    return result
