"""The run gate (core.run): renders each finding at its effective severity + halts iff any effective FAIL;
treatments downgrade/escalate; the build-side has_blocking guard. Hermetic (a temp registry + a list sink)."""
import os
import tempfile

from _harness import run as run_suite, eq, ok
from pipeline4.core import run
from pipeline4.core.finding import Finding
from pipeline4.core.treatments import set_treatment, apply_and_reconcile


def _sink():
    lines = []
    return lines, (lambda level, msg: lines.append((level, msg)))


def test_gate_continue_on_all_warn():
    fs = [Finding(phase=520, type="a", severity="WARN", detail="x"),
          Finding(phase=520, type="b", severity="WARN", detail="y")]
    with tempfile.TemporaryDirectory() as d:
        lines, sink = _sink()
        cont = run.gate(fs, sink, label="520", registry_path=os.path.join(d, "em.csv"))
        ok(cont, "all-WARN -> continue")
        eq(len([l for l in lines if l[0] == "WARN"]), 2, "each finding rendered once at its level")
        ok(not any(l[0] == "FAIL" for l in lines), "no halt line")


def test_gate_halts_on_fail():
    fs = [Finding(phase=520, type="bad", severity="FAIL", detail="undeclared DB")]
    with tempfile.TemporaryDirectory() as d:
        lines, sink = _sink()
        cont = run.gate(fs, sink, label="520", registry_path=os.path.join(d, "em.csv"))
        ok(not cont, "a FAIL -> halt")
        ok(any(l[0] == "FAIL" and "halted" in l[1] for l in lines), "the halt line is appended")


def test_gate_downgrade_unhalts():
    fs = [Finding(phase=520, type="bad", severity="FAIL", detail="undeclared DB")]
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "em.csv")
        apply_and_reconcile(fs, path)                         # register the FAIL
        set_treatment(fs[0].uid, "warn", path)                # operator downgrades it
        lines, sink = _sink()
        cont = run.gate(fs, sink, label="520", registry_path=path)
        ok(cont, "the downgraded FAIL no longer halts the run")
        ok(any(l[0] == "WARN" and "(was FAIL)" in l[1] for l in lines), "rendered as WARN, noting the original")


def test_gate_escalate_halts():
    fs = [Finding(phase=400, type="soft", severity="WARN", detail="a switch not in the DTD")]
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "em.csv")
        apply_and_reconcile(fs, path)
        set_treatment(fs[0].uid, "fail", path)                # operator escalates a WARN to blocking
        lines, sink = _sink()
        ok(not run.gate(fs, sink, label="400", registry_path=path), "the escalated WARN now halts")


def test_has_blocking_raw_guard():
    ok(run.has_blocking([Finding(phase=520, type="x", severity="FAIL", detail="z")]), "raw FAIL blocks the write")
    ok(not run.has_blocking([Finding(phase=520, type="x", severity="WARN", detail="z")]), "WARN does not")


def test_render_never_halts_no_halt_line():
    # render is for WARN-only projection phases (400/510): apply treatments + render, but never a halt line
    fs = [Finding(phase=400, type="if_signal_not_mirrored", severity="WARN", detail="not mirrored")]
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "em.csv")
        apply_and_reconcile(fs, path)
        set_treatment(fs[0].uid, "fail", path)                # even an ESCALATED finding does not halt render
        lines, sink = _sink()
        run.render(fs, sink, registry_path=path)
        ok(any(l[0] == "FAIL" and "(was WARN)" in l[1] for l in lines), "rendered at the escalated level")
        ok(not any("halted" in l[1] for l in lines), "render NEVER prints a halt line (output already written)")


if __name__ == "__main__":
    import sys
    sys.exit(run_suite("run", [
        ("gate_continue_on_all_warn", test_gate_continue_on_all_warn),
        ("gate_halts_on_fail", test_gate_halts_on_fail),
        ("gate_downgrade_unhalts", test_gate_downgrade_unhalts),
        ("gate_escalate_halts", test_gate_escalate_halts),
        ("has_blocking_raw_guard", test_has_blocking_raw_guard),
        ("render_never_halts_no_halt_line", test_render_never_halts_no_halt_line),
    ]))
