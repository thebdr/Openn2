"""The unified log engine (§4.1): EVERY phase logs through ONE engine - the engine emits a
`<number> <Title>` PHASE banner per (sub-)phase, and `ctx.emit(str)` progress strings become
level-inferred LogEntries tagged with that phase. Data-independent: a fake registry/phase, no docs."""
from _harness import run, ok, eq
from pipeline3.phase import Phase, SubPhase, PhaseResult
from pipeline3.context import PipelineContext
from pipeline3 import app
from pipeline3.core.i18n import tr
from pipeline3.core.model import split_level


class _Reg:
    """A minimal registry: topo_order returns the given (already-ordered) phases."""
    def __init__(self, phases):
        self._p = phases

    def topo_order(self, target=None, profile="main"):
        return list(self._p)


def _ctx():
    return PipelineContext(params={}, out_root="", profile="main", lang="en")


def test_engine_emits_phase_banner_with_id():
    def _r(ctx):
        ctx.emit("staging: 5 row(s)")
        return PhaseResult(ok=True, summary="ok")
    ph = Phase(number=300, key="staging", name_key="ph_staging", run=_r, requires=())
    ctx = _ctx()
    app.run_phase(ctx, 300, reg=_Reg([ph]))
    eq(ctx.log[0].level, "PHASE")
    eq(ctx.log[0].phase, 300)
    eq(ctx.log[0].detail, f"300 {tr('ph_staging', 'en')}", "banner reads '<id> <Title>'")


def test_emit_becomes_logentries_under_phase():
    def _r(ctx):
        ctx.emit("staging: 5 rows")
        ctx.emit("  WARN bad sheet")
        ctx.emit("  ERROR locked")
        return PhaseResult(ok=True)
    ph = Phase(number=300, key="staging", name_key="ph_staging", run=_r, requires=())
    ctx = _ctx()
    app.run_phase(ctx, 300, reg=_Reg([ph]))
    body = [(e.level, e.phase, e.detail) for e in ctx.log if e.level != "PHASE"]
    eq(body, [("INFO", 300, "staging: 5 rows"), ("WARN", 300, "bad sheet"), ("FAIL", 300, "locked")],
       "emit strings -> level-inferred, token-stripped LogEntries under the phase")


def test_level_inference_table():
    cases = [("[FAIL] x", ("FAIL", "x")), ("FAIL y", ("FAIL", "y")), ("  WARN z", ("WARN", "z")),
             ("WARNING w", ("WARN", "w")), ("[ERROR] e", ("FAIL", "e")), ("HALT h", ("FAIL", "h")),
             ("[SKIP] s", ("SKIP", "s")), ("PASS p", ("PASS", "p")), ("ORPHAN o", ("INFO", "ORPHAN o")),
             ("staging: 5 rows", ("INFO", "staging: 5 rows"))]
    for msg, expect in cases:
        eq(split_level(msg), expect, f"split_level({msg!r})")


def test_run_subphase_emits_subbanner():
    def _sub(ctx):
        ctx.emit("stage_iolist: 3 rows")
        return PhaseResult(ok=True)
    sub = SubPhase(310, "stage_iolist", "pb_stage_iolist", _sub)
    ctx = _ctx()
    app.run_subphase(ctx, sub)
    eq(ctx.log[0].level, "PHASE")
    eq(ctx.log[0].detail, f"310 {tr('pb_stage_iolist', 'en')}", "sub-banner reads '<id> <Title>'")
    eq((ctx.log[1].level, ctx.log[1].phase), ("INFO", 310))


def test_phase_number_routing():
    def _r200(ctx):
        ctx.emit("fill done")
        return PhaseResult(ok=True)

    def _r300(ctx):
        ctx.emit("stage done")
        return PhaseResult(ok=True)
    p200 = Phase(number=200, key="fill", name_key="ph_fill", run=_r200, requires=())
    p300 = Phase(number=300, key="staging", name_key="ph_staging", run=_r300, requires=(200,))
    ctx = _ctx()
    app.run_phase(ctx, 300, reg=_Reg([p200, p300]))
    eq([(e.phase, e.detail) for e in ctx.log if e.level == "INFO"],
       [(200, "fill done"), (300, "stage done")], "each emit carries its emitter's phase number")
    eq([e.phase for e in ctx.log if e.level == "PHASE"], [200, 300], "one banner per phase")


def test_on_phase_log_hook_fires_per_phase():
    seen = []

    def _r(ctx):
        ctx.emit("a")
        return PhaseResult(ok=True)
    p200 = Phase(number=200, key="fill", name_key="ph_fill", run=_r, requires=())
    p300 = Phase(number=300, key="staging", name_key="ph_staging", run=_r, requires=(200,))
    ctx = _ctx()
    ctx.on_phase_log = lambda entries: seen.append([e.phase for e in entries])
    app.run_phase(ctx, 300, reg=_Reg([p200, p300]))
    eq(seen, [[200, 200], [300, 300]], "hook fires once per phase with that phase's slice (banner+emit)")


if __name__ == "__main__":
    raise SystemExit(run("unified_log", [
        ("engine_emits_phase_banner_with_id", test_engine_emits_phase_banner_with_id),
        ("emit_becomes_logentries_under_phase", test_emit_becomes_logentries_under_phase),
        ("level_inference_table", test_level_inference_table),
        ("run_subphase_emits_subbanner", test_run_subphase_emits_subbanner),
        ("phase_number_routing", test_phase_number_routing),
        ("on_phase_log_hook_fires_per_phase", test_on_phase_log_hook_fires_per_phase),
    ]))
