"""Phase 100c - the two cross-checks (130 CEM->IOL, 140 IOL->CEM) + the ce_refs indexes. Hermetic: the
index builders over synthetic rows, and the run_* functions with `ce_refs.read_ce_refs` monkeypatched to
synthetic C&E refs + a synthetic `signals` Database (no workbook I/O)."""
from _harness import run, eq, ok
from pipeline5.truth.database import Database as DB
from pipeline5.truth.table import Table as CoreTable
from pipeline5.phases.validation import cematrix_refs as ce_refs
from pipeline5.phases.validation import crosscheck
from pipeline5.findings import factory as vm


def _signals(rows):
    t = CoreTable("signals",
                  columns=["uid", "functional_unit", "location", "device", "bit", "source_cell", "desc_l1", "type"],
                  json_columns=["type"], key_columns=["source_cell"])
    for r in rows:
        t.add(**r)
    return DB([t])


def _ref(fu="", lo="", de="", raw_addr="", loc="CE!F6"):
    return {"sheet": "CE", "addr": vm.addr(raw_addr), "raw_addr": raw_addr,
            "key": vm.key(fu, lo, de), "raw_fld": vm.fld_text(fu, lo, de), "loc": loc}


def _patch_refs(refs):
    """Monkeypatch the C&E reader + the file-present guard; returns a restore() callable."""
    orig_read, orig_exists = crosscheck.ce_refs.read_ce_refs, crosscheck.os.path.exists
    crosscheck.ce_refs.read_ce_refs = lambda _p: (list(refs), 1)
    crosscheck.os.path.exists = lambda _p, _o=orig_exists: True if str(_p).endswith(".xlsx") else _o(_p)

    def restore():
        crosscheck.ce_refs.read_ce_refs, crosscheck.os.path.exists = orig_read, orig_exists
    return restore


_PARAMS = {"matrix_path": "ce.xlsx", "iolist_path": "io.xlsx"}


def _types(findings):
    return {(f.type, f.severity) for f in findings}


# --- the indexes ------------------------------------------------------------------------------- #
def test_io_indexes():
    rows = [{"functional_unit": "S1", "location": "L1", "device": "D1", "bit": "I0.0", "source_cell": "IO!5"}]
    by_fld = ce_refs.build_io_index(rows)
    by_addr = ce_refs.build_io_addr_index(rows)
    eq(by_fld[vm.key("S1", "L1", "D1")]["addrs"], {"I0.0"})
    eq(by_addr["I0.0"]["keys"], {vm.key("S1", "L1", "D1")})
    eq(by_addr["I0.0"]["source_cell"], "IO!5")


def test_build_ce_index():
    refs = [_ref("S1", "L1", "D1", "I0.0", "CE!F6")]
    idx = ce_refs.build_ce_index(refs)
    eq(idx["by_key"][vm.key("S1", "L1", "D1")], {"I0.0"})
    eq(idx["by_addr"]["I0.0"], {vm.key("S1", "L1", "D1")})
    eq(idx["loc_by_key"][vm.key("S1", "L1", "D1")], "CE!F6")


def test_ce_match_states():
    idx = ce_refs.build_ce_index([_ref("S1", "L1", "D1", "I0.0")])
    k = vm.key("S1", "L1", "D1")
    eq(crosscheck._ce_match(k, "I0.0", idx), "full")
    eq(crosscheck._ce_match(k, "I9.9", idx), "fld_only", "FLD present, address differs")
    eq(crosscheck._ce_match(vm.key("X"), "I0.0", idx), "addr_only", "address present, FLD differs")
    eq(crosscheck._ce_match(vm.key("X"), "Q9.9", idx), "missing")


# --- 130 CEM -> IOL ---------------------------------------------------------------------------- #
def test_xcheck_cem_iol():
    db = _signals([{"functional_unit": "S1", "location": "L1", "device": "D1", "bit": "I0.0", "source_cell": "IO!5"}])
    refs = [_ref("S1", "L1", "D1", "I0.0", "CE!F6"),    # matches -> cem_addr_ok + cem_fld_ok
            _ref("XX", "", "", "I0.0", "CE!F7"),        # addr there under a DIFFERENT FLD -> cem_addr_fld ONLY
            _ref("ZZ", "", "", "Q9.9", "CE!F8"),        # neither addr nor FLD present -> cem_addr_none + cem_fld_none
            _ref("", "", "", "I1.0", "CE!F9")]          # no device designation -> cem_ref_empty
    restore = _patch_refs(refs)
    try:
        findings = crosscheck.run_xcheck_cem_iol(db, _PARAMS)
    finally:
        restore()
    found = _types(findings)
    for expect in [("cem_addr_ok", "PASS"), ("cem_fld_ok", "PASS"), ("cem_addr_fld", "FAIL"),
                   ("cem_fld_none", "FAIL"), ("cem_addr_none", "FAIL"), ("cem_ref_empty", "FAIL")]:
        ok(expect in found, f"expected {expect}")
    # a cem_addr_fld ref does NOT also emit cem_fld_none (redundant - the address search already says
    # "found under a different FLD"); the only cem_fld_none is the F8 both-missing ref.
    fld_none = [f for f in findings if f.type == "cem_fld_none"]
    eq([f.location for f in fld_none], ["CE!F8"], "cem_fld_none suppressed on a cem_addr_fld row")


# --- 140 IOL -> CEM (the decision tree) -------------------------------------------------------- #
def test_xcheck_iol_cem_decision_tree():
    db = _signals([
        {"functional_unit": "S1", "location": "L1", "device": "D1", "bit": "I0.0", "source_cell": "IO!2",
         "type": {"ce_mandatory": "yes"}},                                          # full match -> iol_cem_match
        {"functional_unit": "S2", "location": "L2", "device": "D2", "bit": "I5.0", "source_cell": "IO!3",
         "type": {"ce_mandatory": "yes"}},                                          # missing -> iol_cem_missing_mandatory
        {"functional_unit": "S3", "location": "L3", "device": "D3", "bit": "I8.0", "source_cell": "IO!4",
         "type": {"ce_mandatory": "no"}},                                           # not required -> SKIP
        {"functional_unit": "S4", "location": "L4", "device": "D4", "bit": "I6.0", "source_cell": "IO!5",
         "desc_l1": "EMERGENCY STOP", "type": None},                               # untyped safety -> missing_safety
        {"functional_unit": "S5", "location": "L5", "device": "D5", "bit": "I7.0", "source_cell": "IO!6",
         "desc_l1": "lamp indicator", "type": None},                               # untyped plain -> unclassified SKIP
    ])
    refs = [_ref("S1", "L1", "D1", "I0.0", "CE!F6")]     # only S1 is in the C&E
    restore = _patch_refs(refs)
    try:
        found = _types(crosscheck.run_xcheck_iol_cem(db, _PARAMS))
    finally:
        restore()
    for expect in [("iol_cem_match", "PASS"), ("iol_cem_missing_mandatory", "FAIL"),
                   ("iol_cem_not_required", "SKIP"), ("iol_cem_missing_safety", "FAIL"),
                   ("iol_cem_unclassified", "SKIP")]:
        ok(expect in found, f"expected {expect}")


def test_xcheck_ce_absent_skips():
    eq([(f.type, f.severity) for f in crosscheck.run_xcheck_cem_iol(_signals([]), {"matrix_path": ""})],
       [("ce_absent", "SKIP")])
    eq([(f.type, f.severity) for f in crosscheck.run_xcheck_iol_cem(_signals([]), {"matrix_path": ""})],
       [("ce_absent", "SKIP")])


if __name__ == "__main__":
    import sys
    sys.exit(run("validation_crosscheck", [
        ("io_indexes", test_io_indexes),
        ("build_ce_index", test_build_ce_index),
        ("ce_match_states", test_ce_match_states),
        ("xcheck_cem_iol", test_xcheck_cem_iol),
        ("xcheck_iol_cem_decision_tree", test_xcheck_iol_cem_decision_tree),
        ("xcheck_ce_absent_skips", test_xcheck_ce_absent_skips),
    ]))
