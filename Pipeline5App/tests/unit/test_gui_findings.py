"""GUI M2 - the Findings panel's pure logic (gui/findings_view.py): the validation_issues ⋈ treatment-registry
join (effective severity), the filters, and the create-or-update 1-click treatment. Tk-free + hermetic."""
import tempfile

from _harness import run, eq, ok
from pipeline5 import config
from pipeline5.findings import treatments
from pipeline5.workbench import findings_view


def _issue(uid, phase, type_, sev, loc="IO!A1", detail="d"):
    return {"uid": uid, "id": f"{phase}-{type_}", "phase": phase, "type": type_,
            "severity": sev, "location": loc, "detail": detail}


def test_panel_rows_effective_severity():
    issues = [_issue("u1", 110, "addr_format", "FAIL"), _issue("u2", 140, "iol_cem_missing_plain", "WARN")]
    issues[0]["location2"], issues[0]["compared"] = "IO!G9", "I0.0 =/= I1.0 | S1 === S1"
    reg = {"u1": treatments.Treatment(uid="u1", treatment="warn")}   # downgrade u1 FAIL -> WARN
    rows = findings_view.panel_rows(issues, reg)
    eq(rows[0]["severity"], "FAIL", "the default is preserved")
    eq(rows[0]["effective"], "WARN", "the treatment downgrades the effective severity")
    eq(rows[0]["treatment"], "warn")
    eq(rows[1]["effective"], "WARN", "an untreated finding keeps its default")
    eq((rows[0]["location2"], rows[0]["compared"]), ("IO!G9", "I0.0 =/= I1.0 | S1 === S1"),
       "the log-line context rides on the panel row")
    eq((rows[1]["location2"], rows[1]["bit"], rows[1]["compared"]), ("", "", ""),
       "an old-schema/plain row defaults its context columns to empty")


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


def test_apply_treatments_bulk():
    """The multi-select treat: every selected row's uid is set in ONE registry write."""
    with tempfile.TemporaryDirectory() as d:
        config.use_project(d)
        try:
            rows = [_issue("m1", 130, "cem_addr_fld", "FAIL"),
                    _issue("m2", 130, "cem_addr_none", "FAIL"),
                    _issue("m3", 140, "iol_cem_missing_plain", "WARN")]
            findings_view.apply_treatments(rows, "warn")
            reg = treatments.load()
            eq({u: reg[u].treatment for u in ("m1", "m2", "m3")},
               {"m1": "warn", "m2": "warn", "m3": "warn"}, "all selected uids treated")
            findings_view.apply_treatments(rows[:2], "")
            reg = treatments.load()
            eq((reg["m1"].treatment, reg["m2"].treatment, reg["m3"].treatment), ("", "", "warn"),
               "a bulk clear touches only the given rows")
        finally:
            config.use_builtin()


def test_apply_and_records():
    from pipeline5.findings.finding import Finding
    with tempfile.TemporaryDirectory() as d:
        config.use_project(d)
        try:
            findings = [Finding(phase=110, type="addr_format", severity="FAIL", detail="bad", location="IO!G5"),
                        Finding(phase=110, type="row_ok", severity="PASS", detail="ok", location="IO!O5")]
            applied, recs = findings_view.apply_and_records(findings)
            eq([eff for _f, eff in applied], ["FAIL", "PASS"], "effective severities (no treatments)")
            eq(recs[0].level, "HEAD", "every rendered group opens with its [HEAD] column-header line")
            line_recs = [r for r in recs if r.level != "HEAD"]
            eq(len(line_recs), 2, "a record per finding")
            eq(line_recs[0].level, "FAIL")
            eq(line_recs[0].uid, findings[0].uid, "the FAIL record carries the finding uid (for the errlink)")
            # render_records does NOT synthesize banners (the handler emits the PHASE banner as a plain line);
            # only severity==PHASE findings render as banners, and plain findings carry none.
            eq([r.kind for r in recs], ["line", "line", "line"], "head + findings are line records, no banner")
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
        ("apply_treatments_bulk", test_apply_treatments_bulk),
        ("apply_and_records", test_apply_and_records),
    ]))
