"""M2 gate: registry topo-sort / presentation order / profiles, and the orchestrator."""
from _harness import run, eq, ok, raises
from pipeline3.phase import Phase, PhaseResult
from pipeline3.registry import PhaseRegistry
from pipeline3.context import PipelineContext
from pipeline3 import app


def _mkrun(order, num, halt=False):
    def _run(ctx):
        order.append(num)
        return PhaseResult(ok=True, halt=halt, summary=f"ran {num}")
    return _run


def _dag(order=None):
    """The real-shaped DAG: 200 -> 300 -> {100,400,...}. Returns a fresh registry."""
    order = order if order is not None else []
    reg = PhaseRegistry()
    reg.register(Phase(200, "fill", "ph_fill", _mkrun(order, 200), requires=()))
    reg.register(Phase(300, "staging", "ph_staging", _mkrun(order, 300), requires=(200,)))
    reg.register(Phase(100, "validation", "ph_validation", _mkrun(order, 100), requires=(300,)))
    reg.register(Phase(400, "interfaces", "ph_interfaces", _mkrun(order, 400), requires=(300,)))
    reg.define_profile("designer", {100, 300})
    return reg, order


def test_presentation_order():
    reg, _ = _dag()
    eq([p.number for p in reg.presentation_order()], [100, 200, 300, 400])


def test_topo_order_full():
    reg, _ = _dag()
    eq([p.number for p in reg.topo_order()], [200, 300, 100, 400])


def test_topo_order_target():
    reg, _ = _dag()
    eq([p.number for p in reg.topo_order(target=400)], [200, 300, 400])
    eq([p.number for p in reg.topo_order(target=200)], [200])


def test_profile_designer():
    reg, _ = _dag()
    eq([p.number for p in reg.presentation_order("designer")], [100, 300])
    # 300's requires=200 is outside the profile, so it is ignored -> 300 then 100
    eq([p.number for p in reg.topo_order(profile="designer")], [300, 100])


def test_duplicate_number_rejected():
    reg, _ = _dag()
    raises(ValueError, lambda: reg.register(Phase(100, "dup", "x", lambda ctx: PhaseResult())))


def test_cycle_detected():
    reg = PhaseRegistry()
    reg.register(Phase(100, "a", "a", lambda ctx: PhaseResult(), requires=(200,)))
    reg.register(Phase(200, "b", "b", lambda ctx: PhaseResult(), requires=(100,)))
    raises(ValueError, lambda: reg.topo_order())


def _ctx(profile="main"):
    return PipelineContext(params={}, out_root="", profile=profile, emit=lambda *_: None)


def test_run_phase_runs_prereqs():
    reg, order = _dag()
    ctx = _ctx()
    app.run_phase(ctx, 400, reg=reg)
    eq(order, [200, 300, 400], "prereqs run in dependency order")
    eq(ctx.completed, {200, 300, 400})


def test_run_phase_memoizes():
    reg, order = _dag()
    ctx = _ctx()
    app.run_phase(ctx, 300, reg=reg)      # runs 200, 300
    app.run_phase(ctx, 400, reg=reg)      # 200/300 already done -> only 400 runs
    eq(order, [200, 300, 400])


def test_run_all_halts():
    order = []
    reg = PhaseRegistry()
    reg.register(Phase(200, "fill", "ph_fill", _mkrun(order, 200, halt=True), requires=()))
    reg.register(Phase(300, "staging", "ph_staging", _mkrun(order, 300), requires=(200,)))
    reg.register(Phase(100, "validation", "ph_v", _mkrun(order, 100), requires=(300,)))
    ctx = _ctx()
    result = app.run_all(ctx, reg=reg)
    ok(result is not None and result.halt)
    eq(order, [200], "halt at 200 stops the run before 300/100")


def test_run_all_full():
    reg, order = _dag()
    ctx = _ctx()
    app.run_all(ctx, reg=reg)
    eq(order, [200, 300, 100, 400])


if __name__ == "__main__":
    raise SystemExit(run("registry", [
        ("presentation_order", test_presentation_order),
        ("topo_order_full", test_topo_order_full),
        ("topo_order_target", test_topo_order_target),
        ("profile_designer", test_profile_designer),
        ("duplicate_number_rejected", test_duplicate_number_rejected),
        ("cycle_detected", test_cycle_detected),
        ("run_phase_runs_prereqs", test_run_phase_runs_prereqs),
        ("run_phase_memoizes", test_run_phase_memoizes),
        ("run_all_halts", test_run_all_halts),
        ("run_all_full", test_run_all_full),
    ]))
