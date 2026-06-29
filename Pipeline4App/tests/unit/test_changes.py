"""ph100 before/after quality report (domain/changes): matching, systematic-event netting, direction +
regression tagging, the node-aware upgrade rule, and the HTML renderer. Hermetic (synthetic rows)."""
from _harness import run, eq, ok

from pipeline4.domain.changes import match, classify, report, run as changes_run


def _row(_row=0, **kw):
    base = dict(functional_unit="", location="", device="", desc_l1="", desc_l1b="",
                connector="", pin_no="", profinet_name="", bit="", type_hw="", slot="", _row=_row)
    base.update(kw)
    return base


WEIGHTS = {"bit": "critical", "type_hw": "critical", "normal_condition": "critical",
           "slot": "major", "desc_l1": "minor", "desc_l1b": "minor", "ts_ref": "exclude"}


def test_norm_keys():
    eq(match.norm("  'Q66307 "), "Q66307", "strip apostrophe + collapse")
    eq(match.norm("SAFETY  RELAY"), "SAFETY RELAY", "collapse internal whitespace")
    eq(match.fld(_row(functional_unit="=S1", location="+A", device="-K1")), "=S1|+A|-K1")
    ok(match.is_blank(_row()), "no fld + no desc = blank spacer")
    ok(not match.is_blank(_row(device="-K1")), "a device makes it non-blank")


def test_assign_nodes():
    rows = [_row(profinet_name="N1", device="-K1"), _row(device="-K2"), _row(profinet_name="N2", device="-K3")]
    match.assign_nodes(rows)
    eq([r["_node"] for r in rows], ["N1", "N1", "N2"], "profinet_name carries down to the next head")


def test_match_iolist_basic():
    # leftovers must land in DIFFERENT nodes - the cascade force-matches leftovers WITHIN a node (so a
    # same-node leftover pair never reads as removed+added; that is the validated "0 removed" property).
    old = [_row(2, profinet_name="N1", device="-K1", desc_l1="CPU"),
           _row(3, device="-K2", desc_l1="SWITCH"),
           _row(4, device="-K3", desc_l1="GONE")]
    new = [_row(2, profinet_name="N1", device="-K1", desc_l1="CPU"),
           _row(3, device="-K2", desc_l1="SWITCH"),
           _row(4, profinet_name="N2", device="-K9", desc_l1="NEW")]
    res = match.match_iolist(old, new)
    eq(len(res["pairs"]), 2, "K1 + K2 match")
    eq([r["device"] for r in res["removed"]], ["-K3"], "K3 removed (no leftover in its node N1)")
    eq([r["device"] for r in res["added"]], ["-K9"], "K9 added (new node N2)")


def test_address_event():
    changes = [(f"I100.{i}", f"I200.{i}") for i in range(10)]
    ev = classify.detect_address_event(changes)
    ok(ev is not None, "10 same-prefix byte-remaps = a systematic event")
    ok(ev["member"]("I100.3", "I200.3"), "a mapped row is a member")
    ok(not ev["member"]("I360.0", "Q360.0"), "an I<->Q prefix flip is NEVER systematic (stays genuine)")
    eq(classify.detect_address_event([("I1.0", "I2.0")]), None, "too few rows -> not systematic")


def test_value_event():
    low = [("-K55", "-K50")] * 6 + [("-K56", "-K51")] * 4        # 2 distinct pairs over 10 rows
    ev = classify.detect_value_event(low)
    ok(ev is not None and ev["member"]("-K55", "-K50"), "low-cardinality bijection = event")
    high = [(f"-K{i}", f"-Q{i}") for i in range(12)]             # 12 distinct pairs
    eq(classify.detect_value_event(high), None, "high-cardinality changes are not a re-map")


def test_classify_systematic_netting():
    # 10 rows whose ONLY change is a byte re-address (systematic) + 1 genuine type gap-fill.
    pairs = []
    for i in range(10):
        o = _row(10 + i, profinet_name="N1", device=f"-K1{i}", desc_l1="RELAY", bit=f"I100.{i}")
        n = _row(10 + i, profinet_name="N1", device=f"-K1{i}", desc_l1="RELAY", bit=f"I200.{i}")
        pairs.append({"old": o, "new": n, "tier": "T1", "confidence": "high"})
    g_o = _row(40, device="-K20", desc_l1="RELAY2", type_hw="")
    g_n = _row(40, device="-K20", desc_l1="RELAY2", type_hw="A")
    pairs.append({"old": g_o, "new": g_n, "tier": "T1", "confidence": "high"})
    res = classify.classify_iolist({"pairs": pairs, "removed": [], "added": []}, WEIGHTS)
    eq(res["systematic_rows"], 10, "the 10 address-only rows are netted out, not counted as defects")
    eq(res["correction_count"], 1, "only the genuine type gap-fill counts")
    eq(res["corrections"][0]["directions"], ["gap-fill"], "blank->value = gap-fill")
    ok(any(e["field"] == "bit" for e in res["systematic_events"]), "the address re-map is an event")


def test_direction_and_regression():
    loss = {"old": _row(1, device="-K1", desc_l1="X", type_hw="PA"),
            "new": _row(1, device="-K1", desc_l1="X", type_hw=""), "tier": "T1", "confidence": "high"}
    res = classify.classify_iolist({"pairs": [loss], "removed": [], "added": []}, WEIGHTS)
    eq(res["correction_count"], 1)
    eq(res["corrections"][0]["directions"], ["value-loss"], "value->blank = value-loss")
    ok(res["corrections"][0]["regression"], "a critical value-loss is a regression")
    eq(len(res["regressions"]), 1, "surfaced in the regressions list")


def test_upgrade_node_aware():
    added = [_row(100 + i, profinet_name="UP", device=f"-K9{i}", desc_l1="FEEDBACK") for i in range(5)]
    added.append(_row(200, profinet_name="OTHER", device="-K1", desc_l1="FORGOTTEN"))
    match.assign_nodes(added)                                   # match_iolist sets _node in production
    res = classify.classify_iolist({"pairs": [], "removed": [], "added": added}, WEIGHTS)
    eq(len(res["upgrades"]), 1, "the 5-row contiguous block is an upgrade")
    eq(res["upgrades"][0]["count"], 5)
    eq(len(res["forgotten"]), 1, "the isolated added row is a forgotten signal, not an upgrade")


def test_channel_block_aggregation():
    pairs = []
    for i in range(3):                                          # 3 channels of one device, attribution uncertain
        o = _row(10 + i, profinet_name="N1", functional_unit="=S1", location="+A", device="-K1",
                 desc_l1="MOTOR", slot=f"-K5{i}")
        n = _row(10 + i, profinet_name="N1", functional_unit="=S1", location="+A", device="-K1",
                 desc_l1="MOTOR", slot=f"-K6{i}")
        pairs.append({"old": o, "new": n, "tier": "T2pos", "confidence": "channel-uncertain"})
    res = classify.classify_iolist({"pairs": pairs, "removed": [], "added": []}, WEIGHTS)
    eq(res["correction_count"], 0, "channel-uncertain rows are not per-row corrections")
    eq(len(res["channel_blocks"]), 1, "they aggregate to one block-level change")
    eq(res["channel_blocks"][0]["channels"], 3, "the block notes its channel count")


def test_render_html_smoke():
    res = classify.classify_iolist({"pairs": [
        {"old": _row(1, device="-K1", desc_l1="X", type_hw="PA"),
         "new": _row(1, device="-K1", desc_l1="X", type_hw=""), "tier": "T1", "confidence": "high"}],
        "removed": [], "added": []}, WEIGHTS)
    res.update({"available": True, "before": "old.xlsx", "after": "new.xlsx",
                "before_rows": 1, "after_rows": 1})
    html = report.render_html({"meta": {"project_code": "T", "generated": "now"},
                               "iolist": res, "cematrix": {"available": False},
                               "area": {"available": False}})
    ok(html.startswith("<!DOCTYPE html>") and "</html>" in html, "a complete HTML document")
    ok("I/O list" in html and "value-loss" in html, "renders the section + the regression")
    ok("&lt;" not in html or "<script" not in html, "no raw script injection")


def test_no_previous_revision():
    same = r"C:\some\file.xlsx"
    result = changes_run.build_report({"iolist_path": same, "iolist_previous_path": same,
                                       "matrix_path": same, "matrix_previous_path": same,
                                       "project_code": "T"}, stamp="now")
    ok(not result["iolist"]["available"], "previous == current -> nothing to compare")
    ok(not result["cematrix"]["available"], "C&E also degrades cleanly")


def test_t5_blank_never_hides_added():
    # a blank spacer old row must NOT force-pair to a NAMED new leftover (which would hide a real add).
    old = [_row(2, profinet_name="N1", device="-K1", desc_l1="CPU"), _row(3, profinet_name="N1")]
    new = [_row(2, profinet_name="N1", device="-K1", desc_l1="CPU"),
           _row(3, profinet_name="N1", device="-K9", desc_l1="NEW SIGNAL")]
    res = match.match_iolist(old, new)
    eq(len(res["pairs"]), 1, "only K1 matches; the blank old stays unmatched")
    eq([r["device"] for r in res["added"]], ["-K9"], "the named new row is reported as added, not hidden")
    eq(res["removed"], [], "the unmatched blank spacer is not a deletion")


def test_subthreshold_rename_is_genuine():
    # a single device-tag fix recovered via T3 (below the bulk threshold) is a GENUINE correction.
    o = _row(3, profinet_name="N1", functional_unit="=S1", location="+A", device="-K1",
             desc_l1="RELAY", connector="X1", pin_no="1")
    n = _row(3, profinet_name="N1", functional_unit="=S1", location="+A", device="-Q9",
             desc_l1="RELAY", connector="X1", pin_no="1")
    res = classify.classify_iolist(
        {"pairs": [{"old": o, "new": n, "tier": "T3", "confidence": "high"}], "removed": [], "added": []},
        {**WEIGHTS, "device": "critical"})
    eq(res["systematic_rows"], 0, "one rename is NOT a systematic event")
    eq(res["correction_count"], 1, "the single device-tag fix is surfaced, not silently netted out")
    eq(res["corrections"][0]["diffs"][0]["field"], "device")


def test_unknown_tier_does_not_crash():
    o = _row(1, device="-K1", desc_l1="X", slot="A")
    n = _row(1, device="-K1", desc_l1="X", slot="B")
    res = classify.classify_iolist({"pairs": [{"old": o, "new": n, "tier": "T1", "confidence": "high"}],
                                    "removed": [], "added": []}, {"slot": "bogus-tier"})
    eq(res["correction_count"], 1, "a hand-edited unknown tier is clamped, not a KeyError")
    eq(sum(res["by_tier"].values()), 1, "the correction still lands in a bucket (minor)")


def test_empty_read_not_green():
    import _harness
    # point at real files that read as EMPTY by using a sheet pattern that matches nothing
    params = {"iolist_path": __file__, "iolist_previous_path": _harness.__file__,
              "matrix_path": __file__, "matrix_previous_path": _harness.__file__,
              "iolist_params": {"sheets": "NO_SUCH_SHEET"}, "project_code": "T"}
    # the .py files are not workbooks -> the read raises -> degrades (covered); the point here is the
    # _why_unavailable / read-guard path returns available False with a reason, never a green report.
    result = changes_run.build_report(params, stamp="now")
    ok(not result["iolist"]["available"], "a non-readable / empty I/O List is never shown as all-clean")


def test_read_error_degrades():
    import _harness                                          # two real files that are NOT workbooks
    a, b = __file__, _harness.__file__
    result = changes_run.build_report({"iolist_path": a, "iolist_previous_path": b,
                                       "matrix_path": a, "matrix_previous_path": b,
                                       "project_code": "T"}, stamp="now")
    ok(not result["iolist"]["available"], "an unreadable workbook degrades, never crashes")
    ok("could not read" in result["iolist"]["reason"], "the reason names the read failure")
    # and the renderer still produces a clean document from the degraded result
    html = report.render_html(result)
    ok(html.startswith("<!DOCTYPE html>") and "</html>" in html, "degraded result still renders")


TESTS = [
    ("norm_keys", test_norm_keys),
    ("assign_nodes", test_assign_nodes),
    ("match_iolist_basic", test_match_iolist_basic),
    ("address_event", test_address_event),
    ("value_event", test_value_event),
    ("classify_systematic_netting", test_classify_systematic_netting),
    ("direction_and_regression", test_direction_and_regression),
    ("upgrade_node_aware", test_upgrade_node_aware),
    ("channel_block_aggregation", test_channel_block_aggregation),
    ("render_html_smoke", test_render_html_smoke),
    ("no_previous_revision", test_no_previous_revision),
    ("t5_blank_never_hides_added", test_t5_blank_never_hides_added),
    ("subthreshold_rename_is_genuine", test_subthreshold_rename_is_genuine),
    ("unknown_tier_does_not_crash", test_unknown_tier_does_not_crash),
    ("empty_read_not_green", test_empty_read_not_green),
    ("read_error_degrades", test_read_error_degrades),
]

if __name__ == "__main__":
    import sys
    sys.exit(run("changes (ph100 before/after report)", TESTS))
