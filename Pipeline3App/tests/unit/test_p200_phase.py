"""M4 gate: phase-200 (Fill) wiring. The header AND the four sub-buttons (210-240) must return a
PhaseResult that the engine's ctx.absorb accepts. Regression: the sub-phases used to return the raw
PopulateResult (no .log/.artifacts) -> 'PopulateResult' object has no attribute 'log' in absorb, AFTER
the I/O List was already written. Data-independent (populate is stubbed; no real workbook needed)."""
from _harness import run, ok, eq
from pipeline3.phase import PhaseResult
from pipeline3.context import PipelineContext
from pipeline3.domain.iolist_diag.populate import PopulateResult
import pipeline3.phases.p200_fillout as p200


def _stub(unresolved=0):
    def fake(params, write=None, out_dir=None, emit=print):
        return PopulateResult(output_path="OUT.xlsx", processed=5, indexed=3, unresolved=unresolved)
    return fake


def test_fill_header_and_subphases_return_phaseresult():
    orig = p200.pop.populate
    p200.pop.populate = _stub()
    try:
        ctx = PipelineContext(params={}, out_root="")
        runners = [("200 header", p200.run)] + [(f"sub {s.number}", s.run) for s in p200.SUB_PHASES]
        for label, fn in runners:
            r = fn(ctx)
            ok(isinstance(r, PhaseResult), f"{label} returns a PhaseResult")
            ctx.absorb(r)                              # the bug site: absorb reads result.log -> must not raise
            eq(r.artifacts.get("populated_iolist"), "OUT.xlsx", f"{label} carries the populated artifact")
            ok(not r.halt, f"{label} does not halt when nothing is unresolved")
        eq(ctx.populated_path, "OUT.xlsx", "_fill set ctx.populated_path")
    finally:
        p200.pop.populate = orig


def test_unresolved_entries_halt():
    orig = p200.pop.populate
    p200.pop.populate = _stub(unresolved=3)
    try:
        ctx = PipelineContext(params={}, out_root="")
        r = p200.SUB_PHASES[1].run(ctx)               # 220 Fill Index
        ok(isinstance(r, PhaseResult) and r.halt and not r.ok, "unresolved -> halting PhaseResult")
        ok("unresolved" in r.summary, "the halt summary names the unresolved entries")
    finally:
        p200.pop.populate = orig


if __name__ == "__main__":
    raise SystemExit(run("p200_phase", [
        ("fill_header_and_subphases_return_phaseresult", test_fill_header_and_subphases_return_phaseresult),
        ("unresolved_entries_halt", test_unresolved_entries_halt),
    ]))
