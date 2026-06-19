"""M3 gate: the single log renderer (complete vs error-only)."""
from _harness import run, ok
from pipeline3.core.model import LogEntry, InfoBlock, banner
from pipeline3.io import render


def _log():
    return [
        banner(100, "PHASE 100 - Documents Validation"),
        LogEntry(level="PASS", phase=110, detail="header ok", info=InfoBlock(bit="I0.0", fld="+MS1")),
        LogEntry(level="SKIP", phase=110, detail="skipped row", info=InfoBlock(fld="+MS2")),
        LogEntry(level="INFO", phase=110, detail="for context"),
        LogEntry(level="WARN", phase=130, detail="A1 vs IOList | I0.0 =/= I0.1", info=InfoBlock(fld="+MS3")),
        LogEntry(level="FAIL", phase=130, detail="missing in C&E", info=InfoBlock(fld="+MS4")),
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
    ok("110-001" in txt, "first 110 entry id")    # PASS is the first non-banner 110 entry
    ok("130-001" in txt, "first 130 entry id")
    ok(":: missing in C&E" in txt, "detail rendered on the right")


def test_reports_helper():
    r = render.reports(_log())
    ok(set(r) == {"complete", "errors"})
    ok(len(r["complete"]) > len(r["errors"]))


if __name__ == "__main__":
    raise SystemExit(run("render", [
        ("complete_has_everything", test_complete_has_everything),
        ("errors_only_drops_pass_skip", test_errors_only_drops_pass_skip),
        ("id_and_detail_present", test_id_and_detail_present),
        ("reports_helper", test_reports_helper),
    ]))
