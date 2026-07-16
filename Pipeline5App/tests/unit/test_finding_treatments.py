"""The treatment registry (core.treatments): effective severity (downgrade + ESCALATE), apply, should_halt,
the reconcile mark-stale policy, and the CSV round-trip. Hermetic (a temp registry path)."""
import os
import tempfile

from _harness import run, eq, ok
from pipeline5.findings import treatments
from pipeline5.findings.finding import Finding
from pipeline5.findings.treatments import Treatment


def _f(uid_phase, type_, sev, detail, loc=""):
    return Finding(phase=uid_phase, type=type_, severity=sev, detail=detail, location=loc)


def test_effective_severity():
    eq(treatments.effective_severity("WARN", ""), "WARN", "blank treatment -> the code default")
    eq(treatments.effective_severity("WARN", "fail"), "FAIL", "ESCALATE a WARN to a halting FAIL")
    eq(treatments.effective_severity("FAIL", "warn"), "WARN", "DOWNGRADE a FAIL so the run proceeds")
    eq(treatments.effective_severity("FAIL", "skip"), "SKIP")
    eq(treatments.effective_severity("ERRR", "ignore"), "SKIP", "ignore -> SKIP")
    eq(treatments.effective_severity("WARN", "W"), "WARN", "single-char treatment works (first-char resolve)")
    eq(treatments.effective_severity("FAIL", "bogus"), "FAIL", "an unknown treatment -> the default")


def test_apply_and_should_halt():
    fs = [_f(520, "a", "FAIL", "x"), _f(520, "b", "WARN", "y")]
    applied = treatments.apply(fs, {})
    eq([eff for _f0, eff in applied], ["FAIL", "WARN"], "no treatments -> defaults, order preserved")
    ok(treatments.should_halt(applied), "a default FAIL halts")
    # downgrade the FAIL -> no halt
    tr = {fs[0].uid: Treatment(uid=fs[0].uid, treatment="warn")}
    applied2 = treatments.apply(fs, tr)
    eq([eff for _f0, eff in applied2], ["WARN", "WARN"])
    ok(not treatments.should_halt(applied2), "the downgraded FAIL no longer halts")
    # escalate the WARN -> halt
    tr2 = {fs[1].uid: Treatment(uid=fs[1].uid, treatment="fail")}
    ok(treatments.should_halt(treatments.apply(fs, tr2)), "the escalated WARN now halts")


def test_csv_round_trip_and_reconcile():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "error_management.csv")
        keep = _f(520, "keep", "FAIL", "still here")
        gone_treated = Treatment(uid="UTREATED", treatment="warn", id="520-old", type="old", message="was here")
        gone_untreated = Treatment(uid="UPLAIN", treatment="", id="520-x", type="x", message="noise")
        # seed the registry with a treatment for `keep` + the two gone rows
        treatments.write(path, {keep.uid: Treatment(uid=keep.uid, treatment="skip"),
                                "UTREATED": gone_treated, "UPLAIN": gone_untreated})
        loaded = treatments.load(path)
        eq(loaded[keep.uid].treatment, "skip", "round-trips the treatment")
        merged = treatments.reconcile([keep], loaded)
        ok(keep.uid in merged and merged[keep.uid].treatment == "skip", "current finding refreshed, treatment kept")
        eq(merged[keep.uid].message, "still here", "context (message) refreshed from the current finding")
        ok("UTREATED" in merged and merged["UTREATED"].status == "stale", "treated-but-gone kept + marked stale")
        ok("UPLAIN" not in merged, "untreated-but-gone pruned (noise)")


def test_apply_and_reconcile_and_set():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "em.csv")
        fs = [_f(520, "a", "FAIL", "boom")]
        treatments.apply_and_reconcile(fs, path)              # first run: registers the FAIL (untreated)
        ok(os.path.exists(path) and fs[0].uid in treatments.load(path), "the FAIL is registered for treatment")
        eq(treatments.set_treatment(fs[0].uid, "warn", path), True, "set a treatment on the existing uid")
        applied = treatments.apply_and_reconcile(fs, path)
        eq(applied[0][1], "WARN", "the set treatment now downgrades the finding")
        eq(treatments.set_treatment("nope", "fail", path), False, "an unknown uid -> False")


def test_non_treatable_not_registered():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "em.csv")
        treatments.apply_and_reconcile([_f(300, "ok", "PASS", "fine"), _f(300, "note", "INFO", "fyi")], path)
        eq(treatments.load(path), {}, "PASS/INFO findings don't get registry rows (only FAIL/ERRR/WARN do)")


if __name__ == "__main__":
    import sys
    sys.exit(run("treatments", [
        ("effective_severity", test_effective_severity),
        ("apply_and_should_halt", test_apply_and_should_halt),
        ("csv_round_trip_and_reconcile", test_csv_round_trip_and_reconcile),
        ("apply_and_reconcile_and_set", test_apply_and_reconcile_and_set),
        ("non_treatable_not_registered", test_non_treatable_not_registered),
    ]))
