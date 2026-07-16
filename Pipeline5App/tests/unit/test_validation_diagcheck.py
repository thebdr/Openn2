"""Phase 100 step 4 - the 150 diagnosis checks (domain/validation/diagcheck.py). Hermetic: synthetic
`signals` + `diagnosis_cabinets` tables. Covers: the virgin-doc SKIP (requires the ph200 fill), the
numeric-pair FAIL, the unknown-cabinet FAIL, slot uniqueness per ALARM/WARNING family (a legitimate
alarm+warning pair on one slot is NOT a collision), and the summary."""
from _harness import run, eq, ok
from pipeline5.core.ssot_database import Database as DB
from pipeline5.core.ssot_table import Table as CoreTable
from pipeline5.domain.validation import diagcheck

_PARAMS = {"iolist_path": "io.xlsx"}


def _db(rows, cabinets=(1, 2)):
    signals = CoreTable("signals",
                        columns=["uid", "functional_unit", "location", "device", "bit", "type",
                                 "type_hw", "diag_cabinet", "diag_bit", "source_sheet", "source_row",
                                 "source_cell"],
                        json_columns=["type"], key_columns=["source_cell"])
    for i, r in enumerate(rows):
        base = {"type": {"in_diag": "x"}, "type_hw": "A", "source_sheet": "IO",
                "source_row": str(10 + i), "source_cell": f"IO!A{10 + i}"}
        base.update(r)
        signals.add(**base)
    cabs = CoreTable("diagnosis_cabinets", columns=["uid", "cabinet_id", "index", "fld"],
                     json_columns=[], key_columns=["cabinet_id"])
    for c in cabinets:
        cabs.add(cabinet_id=c, index=c, fld=f"=S{c}")
    return DB([signals, cabs])


def _types(findings):
    return [(f.type, f.severity) for f in findings]


def test_virgin_doc_skips():
    db = _db([{"diag_cabinet": "", "diag_bit": ""}, {"diag_cabinet": "", "diag_bit": ""}])
    found = _types(diagcheck.run_diag_checks(db, _PARAMS))
    eq(found, [("diag_virgin", "SKIP"), ("diag_summary", "INFO")],
       "a virgin doc -> one SKIP pointing at 200 Fill, nothing else")


def test_unique_and_family_split():
    db = _db([
        {"diag_cabinet": "1", "diag_bit": "0"},                       # ALARM 001.00
        {"diag_cabinet": "1", "diag_bit": "0", "type_hw": "AW"},      # WARNING 001.00 - NOT a collision
        {"diag_cabinet": "2", "diag_bit": "5.0"},                     # float-read numeric parses
    ])
    findings = diagcheck.run_diag_checks(db, _PARAMS)
    found = _types(findings)
    eq(found.count(("diag_unique", "PASS")), 3, "3 unique slots (the alarm/warning pair splits)")
    ok(("diag_dup_slot", "FAIL") not in found, "an alarm+warning pair on one slot is legitimate")
    summary = next(f for f in findings if f.type == "diag_summary")
    ok("3" in summary.detail, "3 in-diagnosis signals checked")


def test_duplicates_invalid_and_unknown_cabinet():
    db = _db([
        {"diag_cabinet": "1", "diag_bit": "3"},                       # dup 1 (ALARM 001.03)
        {"diag_cabinet": "1", "diag_bit": "3"},                       # dup 2
        {"diag_cabinet": "1", "diag_bit": "x"},                       # non-numeric bit -> invalid
        {"diag_cabinet": "", "diag_bit": "4"},                        # missing cabinet -> invalid
        {"diag_cabinet": "9", "diag_bit": "1"},                       # cabinet 9 not in DiagnosisBlocks
    ])
    findings = diagcheck.run_diag_checks(db, _PARAMS)
    dups = [f for f in findings if f.type == "diag_dup_slot"]
    eq(len(dups), 2, "BOTH members of a duplicate slot are flagged")
    ok(all(f.severity == "FAIL" for f in dups))
    ok("001.03" in dups[0].detail and "IO!" in dups[0].detail, "the slot + the other locations named")
    invalid = [f for f in findings if f.type == "diag_invalid"]
    eq(len(invalid), 2, "a non-numeric bit + a missing cabinet are invalid")
    ok("Diag Bit ('x')" in invalid[0].detail, "the offending field + raw value are named")
    unknown = [f for f in findings if f.type == "diag_unknown_cab"]
    eq(len(unknown), 1, "the nonexistent cabinet is flagged")
    ok("9" in unknown[0].detail and unknown[0].severity == "FAIL")
    ok(all(f.doc == "io.xlsx" for f in findings if f.location), "doc-located findings carry the workbook")


def test_non_diag_rows_ignored():
    db = _db([{"type": {}, "diag_cabinet": "1", "diag_bit": "1"},     # not an in-diag type
              {"diag_cabinet": "1", "diag_bit": "2"}])
    findings = diagcheck.run_diag_checks(db, _PARAMS)
    summary = next(f for f in findings if f.type == "diag_summary")
    ok("1" in summary.detail, "only the in-diag signal is checked")


if __name__ == "__main__":
    import sys
    sys.exit(run("validation_diagcheck", [
        ("virgin_doc_skips", test_virgin_doc_skips),
        ("unique_and_family_split", test_unique_and_family_split),
        ("duplicates_invalid_and_unknown_cabinet", test_duplicates_invalid_and_unknown_cabinet),
        ("non_diag_rows_ignored", test_non_diag_rows_ignored),
    ]))
