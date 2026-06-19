"""M3 gate: the single log renderer (complete vs error-only)."""
from _harness import run, ok
from pipeline3.core.model import LogEntry, InfoBlock, banner
from pipeline3.io import render


def _log():
    return [
        banner(100, "PHASE 100 - Documents Validation"),
        LogEntry(level="PASS", phase=110, type="hdr_ok", detail="header ok", info=InfoBlock(bit="I0.0", fld="+MS1")),
        LogEntry(level="SKIP", phase=110, type="row_skip", detail="skipped row", info=InfoBlock(fld="+MS2")),
        LogEntry(level="INFO", phase=110, type="ctx", detail="for context"),
        LogEntry(level="WARN", phase=130, type="xc_warn", detail="A1 vs IOList | I0.0 =/= I0.1",
                 location="AREA 1!F5", doc="CEMatrix.xlsx",
                 location2="NET SAFETY 50!O30", doc2="IOList.xlsx", info=InfoBlock(fld="+MS3")),
        LogEntry(level="FAIL", phase=130, type="xc_fail", detail="missing in C&E", info=InfoBlock(fld="+MS4")),
    ]


def test_complete_has_everything():
    txt = render.render_text(_log(), errors_only=False)
    for s in ("header ok", "skipped row", "for context", "A1 vs IOList", "missing in C&E"):
        ok(s in txt, f"missing {s!r}")
    ok("PHASE 100" in txt)


def test_errors_only_drops_pass_skip():
    txt = render.render_text(_log(), errors_only=True)
    ok("header ok" not in txt, "PASS dropped")
    ok("skipped row" not in txt, "SKIP dropped")
    # but PHASE header + INFO + WARN + FAIL kept
    ok("PHASE 100" in txt)
    ok("for context" in txt, "INFO kept")
    ok("A1 vs IOList" in txt, "WARN kept")
    ok("missing in C&E" in txt, "FAIL kept")


def test_id_and_detail_present():
    txt = render.render_text(_log(), errors_only=False)
    ok("110-hdr_ok" in txt, "log-type index <phase>-<type> rendered")
    ok("130-xc_warn" in txt, "130 entry log-type index")
    ok(":: missing in C&E" in txt, "detail rendered on the right")


def test_location_has_no_workbook_name():
    txt = render.render_text(_log(), errors_only=False)
    ok("AREA 1!F5" in txt, "the sheet!cell link is rendered")
    ok("NET SAFETY 50!O30" in txt, "the second-workbook (location2) link is rendered")
    ok("CEMatrix.xlsx" not in txt and "IOList.xlsx" not in txt, "no workbook name (doc/doc2) is rendered")


def test_reports_helper():
    r = render.reports(_log())
    ok(set(r) == {"complete", "errors"})
    ok(len(r["complete"]) > len(r["errors"]))


if __name__ == "__main__":
    raise SystemExit(run("render", [
        ("complete_has_everything", test_complete_has_everything),
        ("errors_only_drops_pass_skip", test_errors_only_drops_pass_skip),
        ("id_and_detail_present", test_id_and_detail_present),
        ("location_has_no_workbook_name", test_location_has_no_workbook_name),
        ("reports_helper", test_reports_helper),
    ]))
