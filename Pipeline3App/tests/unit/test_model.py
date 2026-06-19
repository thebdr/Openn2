"""M1 gate: the LogEntry model - id formatting, uid stability, seq numbering."""
from _harness import run, eq, ok
from pipeline3.core.model import LogEntry, InfoBlock, number_entries, banner, ERROR_REPORT_LEVELS


def test_id_format():
    e = LogEntry(level="FAIL", phase=130, seq=7)
    eq(e.id, "130-007")
    eq(LogEntry(level="WARN", phase=110, seq=123).id, "110-123")


def test_uid_stable_across_level_and_seq():
    a = LogEntry(level="FAIL", phase=130, type="t", location="IOList!A1", detail="x vs y", seq=1)
    b = LogEntry(level="WARN", phase=130, type="t", location="IOList!A1", detail="x vs y", seq=99)
    eq(a.uid, b.uid, "uid must ignore level + seq")


def test_uid_varies_with_finding():
    base = LogEntry(level="FAIL", phase=130, type="t", location="IOList!A1", detail="x vs y")
    ok(base.uid != LogEntry(level="FAIL", phase=130, type="t", location="IOList!A2", detail="x vs y").uid)
    ok(base.uid != LogEntry(level="FAIL", phase=140, type="t", location="IOList!A1", detail="x vs y").uid)
    ok(base.uid != LogEntry(level="FAIL", phase=130, type="t", location="IOList!A1", detail="x vs z").uid)


def test_uid_normalizes_whitespace():
    a = LogEntry(level="FAIL", phase=130, type="t", location="IOList!A1", detail="x   vs  y")
    b = LogEntry(level="FAIL", phase=130, type="t", location="IOList!A1", detail="x vs y")
    eq(a.uid, b.uid, "uid must whitespace-normalize the detail")


def test_number_entries_per_phase():
    entries = [
        banner(100, "PHASE 100"),
        LogEntry(level="FAIL", phase=110),
        LogEntry(level="PASS", phase=110),
        LogEntry(level="FAIL", phase=130),
        LogEntry(level="WARN", phase=110),
    ]
    number_entries(entries)
    eq([e.seq for e in entries], [0, 1, 2, 1, 3], "seq increments per phase, banners skipped")
    eq(entries[1].id, "110-001")
    eq(entries[4].id, "110-003")
    eq(entries[3].id, "130-001")


def test_error_report_levels():
    ok("PASS" not in ERROR_REPORT_LEVELS and "SKIP" not in ERROR_REPORT_LEVELS)
    for lv in ("PHASE", "INFO", "WARN", "FAIL"):
        ok(lv in ERROR_REPORT_LEVELS, lv)


def test_infoblock_cells():
    ib = InfoBlock(bit="I0.0", fld="+MS1.CC1", desc_l1="d1")
    eq(ib.cells(), ["I0.0", "+MS1.CC1", "d1", "", "", ""])


if __name__ == "__main__":
    raise SystemExit(run("model", [
        ("id_format", test_id_format),
        ("uid_stable_across_level_and_seq", test_uid_stable_across_level_and_seq),
        ("uid_varies_with_finding", test_uid_varies_with_finding),
        ("uid_normalizes_whitespace", test_uid_normalizes_whitespace),
        ("number_entries_per_phase", test_number_entries_per_phase),
        ("error_report_levels", test_error_report_levels),
        ("infoblock_cells", test_infoblock_cells),
    ]))
