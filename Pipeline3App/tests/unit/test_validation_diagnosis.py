"""M6 gate (data-independent): 150 Validate Diagnosis Assignments.

(Diag Cabinet, Diag Bit) must be numeric and unique within the alarm/warning family. A legitimate
alarm+warning pair on the same (cabinet,bit) is NOT a collision (different families).
"""
from _harness import run, eq, ok

from pipeline3.context import PipelineContext
from pipeline3.domain.validation import run_diagnosis


def _row(cab, bit, type_hw, srow, in_diag=True):
    return {"diag_cabinet": cab, "diag_bit": bit, "type_hw": type_hw,
            "_source_sheet": "NET SAFETY 50", "_source_row": srow, "source_cell": f"NET SAFETY 50!O{srow}",
            "functional_unit": "=S", "location": "+M", "device": f"-D{srow}", "bit": "",
            "script_type": "A", "index": "", "desc_l1": "", "desc_l1b": "", "drawing": "",
            "_type": {"in_diagnosis": in_diag}}


def _run(rows):
    ctx = PipelineContext(params={"io_list": {"path": "X/IOList.xlsx", "sheet": "x", "header_row": 1}},
                          out_root="X", rows=rows, lang="en", profile="main")
    return run_diagnosis(ctx)


def test_invalid_dup_unique_and_family():
    rows = [
        _row("2", "x", "A", 5),            # diag_invalid (bit non-numeric)
        _row("3", "5", "A", 6),            # dup slot 003.05 ALARM ...
        _row("3", "5", "A", 7),            # ... with this one
        _row("3", "6", "A", 8),            # unique 003.06 ALARM
        _row("4", "7", "A", 9),            # ALARM 004.07
        _row("4", "7", "AW", 10),          # WARNING 004.07 -> NOT a collision
        _row("9", "9", "A", 11, in_diag=False),   # not in diagnosis -> ignored
    ]
    out = _run(rows)
    types = [x.type for x in out]
    ok("diag_invalid" in types)
    eq(types.count("diag_dup_slot"), 2, "both members of slot 003.05 ALARM")
    eq(types.count("diag_unique"), 3, "003.06 ALARM + the alarm/warning pair on 004.07")
    summ = next(x for x in out if x.type == "diag_summary")
    ok("6" in summ.detail, "6 in-diagnosis signals checked (the non-diag row excluded)")


def test_invalid_points_at_bit_cell_and_links_clean():
    out = _run([_row("2", "x", "A", 5)])
    inv = next(x for x in out if x.type == "diag_invalid")
    eq(inv.level, "FAIL")
    eq(inv.location, "NET SAFETY 50!AF5", "bad bit -> AF cell")
    ok(".xlsx" not in inv.location)


def _crow(cab, container_check, fullname, srow, fu="=S1", loc="+M1"):
    """An in-diagnosis row carrying a diag_container_check template + the cabinet's staged FullName."""
    return {"diag_cabinet": cab, "diag_bit": str(srow), "type_hw": "A",
            "_source_sheet": "NET SAFETY 50", "_source_row": srow, "source_cell": f"NET SAFETY 50!O{srow}",
            "functional_unit": fu, "location": loc, "device": f"-D{srow}", "bit": "",
            "script_type": "A", "index": "", "desc_l1": "", "desc_l1b": "", "drawing": "",
            "diag_block_name": fullname,
            "_type": {"in_diagnosis": True, "diag_container_check": container_check}}


def test_diag_container_check():
    rows = [
        _crow("0", "{functional_unit}{location}", "=S1+M1", 5, fu="=S1", loc="+M1"),       # node match -> PASS
        _crow("1", "breaker", "=S1+SafetyBreakers_1", 6),                                  # literal, case-insens -> PASS
        _crow("2", "{functional_unit}{location}|Field", "=S1+FieldIODevices_1", 7, loc="+X9"),  # the 'Field' alt -> PASS
        _crow("3", "door", "=S1+SafetyBreakers_1", 8),                                     # 'door' not in FullName -> FAIL
        _crow("4", "{functional_unit}{location}", "", 9),                                  # cabinet not in DiagBlocks -> FAIL
    ]
    out = _run(rows)
    by = {}
    for x in out:
        by.setdefault(x.type, []).append(x)
    eq(len(by.get("diag_container_ok", [])), 3, "the 3 matching containers PASS")
    bad = by.get("diag_container_bad", [])
    eq(len(bad), 2, "the door-mismatch + the empty-FullName FAIL")
    door = next(x for x in bad if x.location == "NET SAFETY 50!AE8")
    eq(door.level, "FAIL")
    ok("door" in door.detail.lower() and "safetybreakers" in door.detail.lower(),
       "the detail names the expected container + the actual FullName")
    none = next(x for x in bad if x.location == "NET SAFETY 50!AE9")
    ok("(none)" in none.detail, "an unresolved cabinet shows '(none)' as the actual FullName")


if __name__ == "__main__":
    raise SystemExit(run("validation_diagnosis", [
        ("invalid_dup_unique_and_family", test_invalid_dup_unique_and_family),
        ("invalid_points_at_bit_cell_and_links_clean", test_invalid_points_at_bit_cell_and_links_clean),
        ("diag_container_check", test_diag_container_check),
    ]))
