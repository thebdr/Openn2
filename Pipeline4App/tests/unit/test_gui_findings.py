"""GUI M2 - the Findings panel's pure logic (gui/findings_view.py): the validation_issues ⋈ treatment-registry
join (effective severity), the filters, and the create-or-update 1-click treatment. Tk-free + hermetic."""
import tempfile

from _harness import run, eq, ok
from pipeline4.core import config, treatments
from pipeline4.gui import findings_view


def _issue(uid, phase, type_, sev, loc="IO!A1", detail="d"):
    return {"uid": uid, "id": f"{phase}-{type_}", "phase": phase, "type": type_,
            "severity": sev, "location": loc, "detail": detail}


def test_panel_rows_effective_severity():
    issues = [_issue("u1", 110, "addr_format", "FAIL"), _issue("u2", 140, "iol_cem_missing_plain", "WARN")]
    reg = {"u1": treatments.Treatment(uid="u1", treatment="warn")}   # downgrade u1 FAIL -> WARN
    rows = findings_view.panel_rows(issues, reg)
    eq(rows[0]["severity"], "FAIL", "the default is preserved")
    eq(rows[0]["effective"], "WARN", "the treatment downgrades the effective severity")
    eq(rows[0]["treatment"], "warn")
    eq(rows[1]["effective"], "WARN", "an untreated finding keeps its default")


def test_filter_rows():
    rows = findings_view.panel_rows(
        [_issue("u1", 110, "a", "FAIL"), _issue("u2", 140, "b", "WARN")], {})
    eq([r["uid"] for r in findings_view.filter_rows(rows, phase="110")], ["u1"], "phase filter")
    eq([r["uid"] for r in findings_view.filter_rows(rows, severity="WARN")], ["u2"], "effective-severity filter")
    eq(len(findings_view.filter_rows(rows)), 2, "no filter -> all")


def test_apply_treatment_create_and_update():
    with tempfile.TemporaryDirectory() as d:
        config.use_project(d)
        try:
            row = _issue("u9", 130, "cem_addr_none", "FAIL", loc="CE!F6", detail="addr not found")
            # the uid is NOT yet in the registry -> apply_treatment must CREATE it (set_treatment would no-op)
            findings_view.apply_treatment("u9", "skip", row)
            reg = treatments.load()
            ok("u9" in reg and reg["u9"].treatment == "skip", "created the registry row")
            eq(reg["u9"].type, "cem_addr_none", "carries the finding context")
            eq(reg["u9"].location, "CE!F6")
            # now UPDATE it
            findings_view.apply_treatment("u9", "warn", row)
            eq(treatments.load()["u9"].treatment, "warn", "updated the existing row")
            # clear it
            findings_view.apply_treatment("u9", "", row)
            eq(treatments.load()["u9"].treatment, "", "cleared the treatment")
        finally:
            config.use_builtin()


def test_apply_and_records():
    from pipeline4.core.finding import Finding
    with tempfile.TemporaryDirectory() as d:
        config.use_project(d)
        try:
            findings = [Finding(phase=110, type="addr_format", severity="FAIL", detail="bad", location="IO!G5"),
                        Finding(phase=110, type="row_ok", severity="PASS", detail="ok", location="IO!O5")]
            applied, recs = findings_view.apply_and_records(findings)
            eq([eff for _f, eff in applied], ["FAIL", "PASS"], "effective severities (no treatments)")
            line_recs = [r for r in recs if r.kind == "line"]
            eq(len(line_recs), 2, "a record per finding")
            eq(line_recs[0].level, "FAIL")
            eq(line_recs[0].uid, findings[0].uid, "the FAIL record carries the finding uid (for the errlink)")
            # render_records does NOT synthesize banners (the handler emits the PHASE banner as a plain line);
            # only severity==PHASE findings render as banners, and plain findings carry none.
            eq([r.kind for r in recs], ["line", "line"], "plain findings -> line records only, no banner")
            # a treatment now downgrades the rendered level
            findings_view.apply_treatment(findings[0].uid, "warn", {"phase": 110, "type": "addr_format"})
            applied2, _r = findings_view.apply_and_records(findings)
            eq(applied2[0][1], "WARN", "the registry downgrade is reflected in the records' effective severity")
        finally:
            config.use_builtin()


if __name__ == "__main__":
    import sys
    sys.exit(run("gui_findings", [
        ("panel_rows_effective_severity", test_panel_rows_effective_severity),
        ("filter_rows", test_filter_rows),
        ("apply_treatment_create_and_update", test_apply_treatment_create_and_update),
        ("apply_and_records", test_apply_and_records),
    ]))
