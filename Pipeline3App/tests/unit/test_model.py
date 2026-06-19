"""M1 gate: the LogEntry model - id formatting, uid stability, seq numbering."""
from _harness import run, eq, ok
from pipeline3.core.model import LogEntry, InfoBlock, number_entries, banner, ERROR_REPORT_LEVELS


def test_id_is_phase_and_type():
    e = LogEntry(level="FAIL", phase=130, type="cem_match")
    eq(e.id, "130-cem_match", "id is the code-traceable log-type index <phase>-<type>")
    eq(LogEntry(level="WARN", phase=110, type="addr_format").id, "110-addr_format")
    eq(LogEntry(level="INFO", phase=110).id, "110", "no type -> just the phase")


def test_uid_stable_across_level_and_seq():
    a = LogEntry(level="FAIL", phase=130, type="t", location="IOList!A1", detail="x vs y", seq=1)
    b = LogEntry(level="WARN", phase=130, type="t", location="IOList!A1", detail="x vs y", seq=99)
    eq(a.uid, b.uid, "uid must ignore level + seq")


def test_uid_unchanged_when_doc_changes():
    # revision-stability: the workbook identity (doc) is NOT part of the uid, so a finding keeps the
    # same uid across a document revision (renamed/updated input file).
    a = LogEntry(level="FAIL", phase=130, type="t", location="NET!A1", detail="x", doc="IOList_v1.xlsx")
    b = LogEntry(level="FAIL", phase=130, type="t", location="NET!A1", detail="x", doc="IOList_v2.xlsx")
    eq(a.uid, b.uid, "uid must ignore the workbook identity")


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
        LogEntry(level="FAIL", phase=110, type="a"),
        LogEntry(level="PASS", phase=110, type="b"),
        LogEntry(level="FAIL", phase=130, type="c"),
        LogEntry(level="WARN", phase=110, type="d"),
    ]
    number_entries(entries)
    eq([e.seq for e in entries], [0, 1, 2, 1, 3], "seq increments per phase, banners skipped")
    eq(entries[1].id, "110-a")
    eq(entries[4].id, "110-d")
    eq(entries[3].id, "130-c")


def test_error_report_levels():
    ok("PASS" not in ERROR_REPORT_LEVELS and "SKIP" not in ERROR_REPORT_LEVELS)
    for lv in ("PHASE", "INFO", "WARN", "FAIL"):
        ok(lv in ERROR_REPORT_LEVELS, lv)


def test_infoblock_cells():
    ib = InfoBlock(bit="I0.0", fld="+MS1.CC1", desc_l1="d1")
    eq(ib.cells(), ["I0.0", "+MS1.CC1", "d1", "", "", ""])


if __name__ == "__main__":
    raise SystemExit(run("model", [
        ("id_is_phase_and_type", test_id_is_phase_and_type),
        ("uid_stable_across_level_and_seq", test_uid_stable_across_level_and_seq),
        ("uid_unchanged_when_doc_changes", test_uid_unchanged_when_doc_changes),
        ("uid_varies_with_finding", test_uid_varies_with_finding),
        ("uid_normalizes_whitespace", test_uid_normalizes_whitespace),
        ("number_entries_per_phase", test_number_entries_per_phase),
        ("error_report_levels", test_error_report_levels),
        ("infoblock_cells", test_infoblock_cells),
    ]))
