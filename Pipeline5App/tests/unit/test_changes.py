"""ph100 before/after quality report (domain/changes): matching, systematic-event netting, direction +
regression tagging, the node-aware upgrade rule, and the HTML renderer. Hermetic (synthetic rows)."""
from _harness import run, eq, ok

from pipeline5.phases.changes import match
from pipeline5.phases.changes import classify
from pipeline5.phases.changes import report
from pipeline5.phases.changes import report_runner as changes_run


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


def test_address_grouped_not_hidden():
    # 10 rows whose ONLY change is a byte re-address + 1 type gap-fill. Address must be COUNTED + grouped
    # by node (NOT hidden), because a re-addressing is the costliest correction to apply on the machine.
    pairs = []
    for i in range(10):
        o = _row(10 + i, _node="N1", device=f"-K1{i}", desc_l1="RELAY", bit=f"I100.{i}")
        n = _row(10 + i, _node="N1", device=f"-K1{i}", desc_l1="RELAY", bit=f"I200.{i}")
        pairs.append({"old": o, "new": n, "tier": "T1", "confidence": "high"})
    pairs.append({"old": _row(40, _node="N1", device="-K20", desc_l1="RELAY2", type_hw=""),
                  "new": _row(40, _node="N1", device="-K20", desc_l1="RELAY2", type_hw="A"),
                  "tier": "T1", "confidence": "high"})
    res = classify.classify_iolist({"pairs": pairs, "removed": [], "added": []}, WEIGHTS)
    eq(res["structural_rows"], 10, "the 10 address changes are COUNTED (not hidden)")
    grp = [g for g in res["grouped_changes"] if g["field"] == "bit"]
    eq(len(grp), 1, "grouped into one (node, address) entry")
    eq((grp[0]["node"], grp[0]["count"], grp[0]["tier"]), ("N1", 10, "critical"), "node N1, 10 rows, critical")
    eq(grp[0]["changes"][0], ("I100.0", "I200.0"), "the actual old->new address values are kept for the drill-down")
    eq(len(grp[0]["changes"]), 10, "all 10 address changes are retained")
    eq(res["by_tier"]["critical"], 11, "all 11 changed rows read critical (10 address + 1 type)")
    eq(res["correction_count"], 1, "the type gap-fill is itemized; address rows are grouped, not itemized")
    eq(res["corrections"][0]["directions"], ["gap-fill"], "blank->value = gap-fill")


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
                 desc_l1="MOTOR", desc_l1b=str(i))             # an itemized (semantic) change, not structural
        n = _row(10 + i, profinet_name="N1", functional_unit="=S1", location="+A", device="-K1",
                 desc_l1="PUMP", desc_l1b=str(i))
        pairs.append({"old": o, "new": n, "tier": "T2pos", "confidence": "channel-uncertain"})
    res = classify.classify_iolist({"pairs": pairs, "removed": [], "added": []}, WEIGHTS)
    eq(res["correction_count"], 3, "channel-uncertain rows ARE corrections (merged into the one list)")
    blocks = [b for b in res["correction_blocks"] if b["confidence"] == "channel-uncertain"]
    eq(len(blocks), 1, "they aggregate to one node block, flagged channel-uncertain")
    eq(blocks[0]["count"], 3, "the block notes its row/channel count")
    flds = {f["field"] for f in blocks[0]["fields"]}
    ok("desc_l1" in flds, "the block carries WHAT changed (the field), not just a count")
    eq(blocks[0]["fields"][0]["values"], [("MOTOR", "PUMP")] * 3, "the per-channel old->new values are kept")


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
    eq(res["structural_rows"], 0, "one sub-threshold rename is NOT bulk-grouped")
    eq(res["correction_count"], 1, "the single device-tag fix is surfaced as an itemized correction")
    eq(res["corrections"][0]["diffs"][0]["field"], "device")


def test_unknown_tier_does_not_crash():
    o = _row(1, device="-K1", desc_l1="X", slot="A")
    n = _row(1, device="-K1", desc_l1="X", slot="B")
    res = classify.classify_iolist({"pairs": [{"old": o, "new": n, "tier": "T1", "confidence": "high"}],
                                    "removed": [], "added": []}, {"slot": "bogus-tier"})
    eq(res["structural_rows"], 1, "the slot change is grouped + counted, not a KeyError")
    eq(sum(res["by_tier"].values()), 1, "a hand-edited unknown tier is clamped into a bucket (minor)")


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


def test_address_decompose():
    eq(report._decompose("I922.0"), ("I", ["922", "0"]), "Siemens-compact -> prefix + [byte, bit]")
    eq(report._decompose("I.10.0.0"), ("I", ["10", "0", "0"]), "node-qualified -> prefix + [node, byte, bit]")
    eq(report._decompose("Q130.5"), ("Q", ["130", "5"]), "output prefix")
    eq(report._decompose("notanaddr"), None, "non-address -> None")
    eq(report._decompose("10000"), None, "a bare number is not an address")


def test_address_lines_classify():
    reloc = report._address_lines([("I700.0", "I600.0"), ("I700.1", "I600.1"), ("I700.2", "I600.2")])
    ok("Byte relocation" in reloc and "700" in reloc and "600" in reloc, "byte changed, bit same -> relocation")
    shuf = report._address_lines([("I620.1", "I620.4"), ("I620.2", "I620.1")])
    ok("Bit reshuffle in I620" in shuf, "same byte, bit changed -> reshuffle")
    flip = report._address_lines([("I360.0", "Q360.0")])
    ok("Direction flip" in flip and "input→output" in flip, "prefix changed -> in/out flip (highlighted)")
    move = report._address_lines([("I.10.0.0", "I.12.0.0")])
    ok("Node move" in move, "node coord changed -> node move")


def test_fld_noise_predicate():
    ok(classify._fld_noise("-'Q66305..6", "-Q66305..6"), "a stray text-guard apostrophe = noise")
    ok(classify._fld_noise("=S1 +A", "=S1+A"), "whitespace-only change = noise")
    ok(classify._fld_noise("-K66901", "-K66902"), "one alphanumeric char (1->2) = noise")
    ok(not classify._fld_noise("-K66901", "-K77902"), "several alphanumeric chars differ = NOT noise")
    ok(not classify._fld_noise("-K1", "-K123"), "two added chars = NOT noise")


def test_fld_noise_category():
    # a row whose ONLY change is a noise FLD edit -> the noise listing, NOT corrections; counts unchanged.
    o = _row(1, profinet_name="N1", functional_unit="=S1", location="+A", device="-'K1", desc_l1="RELAY")
    n = _row(1, profinet_name="N1", functional_unit="=S1", location="+A", device="-K1", desc_l1="RELAY")
    res = classify.classify_iolist(
        {"pairs": [{"old": o, "new": n, "tier": "T1", "confidence": "high"}], "removed": [], "added": []},
        {**WEIGHTS, "device": "critical"})
    eq(res["correction_count"], 0, "the apostrophe-only FLD change is NOT a real correction")
    eq(len(res["noise_blocks"]), 1, "it lands in the noise category")
    eq(res["by_tier"]["critical"], 1, "but the row is still counted in by_tier - the change is listing-only")


def test_by_nature_partitions_changed():
    # every CHANGED row is bucketed once by its costliest nature: address re-map > pure completion > other.
    old = [_row(1, profinet_name="N1", desc_l1="A", bit="I0.0"),       # address change
           _row(2, profinet_name="N1", desc_l1="B", desc_l1b=""),      # a blank -> filled = completion
           _row(3, profinet_name="N1", desc_l1="C", type_hw="X")]      # a value change = other
    new = [_row(1, profinet_name="N1", desc_l1="A", bit="I10.0"),
           _row(2, profinet_name="N1", desc_l1="B", desc_l1b="FILLED"),
           _row(3, profinet_name="N1", desc_l1="C", type_hw="Y")]
    res = classify.classify_iolist(match.match_iolist(old, new), WEIGHTS)
    nat = res["by_nature"]
    eq(sum(nat.values()), res["changed"], "by_nature partitions every changed row exactly once (sums to changed)")
    eq(nat["address"], 1, "the bit change -> address bucket")
    eq(nat["completion"], 1, "the blank -> filled change -> completion bucket")
    eq(nat["other"], 1, "the type_hw value change -> other bucket")


def test_struck_rows_counted():
    # a row whose new revision carries a struck-through cell (_struck) is counted (formatting to flag).
    old = [_row(1, profinet_name="N1", desc_l1="A"), _row(2, profinet_name="N1", desc_l1="B")]
    new = [_row(1, profinet_name="N1", desc_l1="A"), _row(2, profinet_name="N1", desc_l1="B")]
    new[0]["_struck"] = True
    res = classify.classify_iolist(match.match_iolist(old, new), WEIGHTS)
    eq(res["struck_rows"], 1, "the one struck-through new row is counted")


def _arow(sheet, dev, line, out, desc):
    return {"_sheet": sheet, "device_tag": dev, "line_numbering": line, "digital_output": out, "description": desc}


def test_area_multi_area_device_not_moved():
    # a device legitimately present in TWO area sheets must pair SAME-area, NOT be reported as a move.
    old = [_arow("AREA 1", "-K1", "L1", "Q1", "PUMP"), _arow("AREA 2", "-K1", "L1", "Q1", "PUMP")]
    new = [_arow("AREA 1", "-K1", "L1", "Q1", "PUMP"), _arow("AREA 2", "-K1", "L1", "Q1", "PUMP")]
    mr = match.match_area(old, new)
    eq(len(mr["pairs"]), 2, "both area appearances pair")
    eq(sum(1 for p in mr["pairs"] if p["moved"]), 0, "a device spanning two areas is NOT a move")


def test_area_genuine_move_detected():
    # a device that actually changed AREA sheet (no same-area counterpart) IS a move.
    mr = match.match_area([_arow("AREA 1", "-K1", "L1", "Q1", "PUMP")],
                          [_arow("AREA 2", "-K1", "L1", "Q1", "PUMP")])
    eq(len(mr["pairs"]), 1, "matched across sheets")
    eq(mr["pairs"][0]["moved"], True, "a genuine sheet change IS a move")


def test_area_membership_extended_and_moved():
    # device-centric area membership: K1 gains AREA 2 (extended = design grew); K2 moves AREA 3 -> AREA 4.
    def pair(o, n):
        return {"old": o, "new": n, "moved": o["_sheet"] != n["_sheet"]}
    pairs = [pair(_arow("AREA 1", "-K1", "L1", "Q1", "PUMP"), _arow("AREA 1", "-K1", "L1", "Q1", "PUMP")),
             pair(_arow("AREA 3", "-K2", "L2", "Q2", "FAN"), _arow("AREA 4", "-K2", "L2", "Q2", "FAN"))]
    added = [_arow("AREA 2", "-K1", "L3", "Q3", "PUMP")]          # K1 copied into a 2nd area (no old counterpart)
    mr = {"pairs": pairs, "removed": [], "added": added}
    res = classify.classify_area(mr, {"AREA 1": 1, "AREA 3": 1}, {"AREA 1": 1, "AREA 2": 1, "AREA 4": 1},
                                 {"device_tag": "critical"})
    eq(res["membership_summary"]["extended"], 1, "K1 gained AREA 2 with none removed -> extended")
    eq(res["membership_summary"]["moved"], 1, "K2 AREA 3 -> AREA 4 -> moved")
    mem = {m["device_tag"]: m for m in res["membership"]}
    eq(mem["-K1"]["new_areas"], ["AREA 1", "AREA 2"], "K1 now spans AREA 1 + AREA 2")
    eq(mem["-K1"]["added"], ["AREA 2"], "AREA 2 is the added zone")


def test_area_device_tag_noise():
    # a moved AREA row whose ONLY itemized change is a punctuation device_tag cleanup (--K -> -K):
    # the move stays (safety), the device_tag change is split into the AREA noise listing, counts unchanged.
    old = {"_sheet": "AREA 1", "device_tag": "=S1+UL1.CC1--K66901", "digital_output": "Q640.0",
           "line_numbering": "L1", "description": "TELESCOPIC BELTS"}
    new = {"_sheet": "AREA 2", "device_tag": "=S1+UL1.CC1-K66901", "digital_output": "Q640.0",
           "line_numbering": "L1", "description": "TELESCOPIC BELTS"}
    mr = {"pairs": [{"old": old, "new": new, "moved": True}], "removed": [], "added": []}
    res = classify.classify_area(mr, {"AREA 1": 1}, {"AREA 2": 1},
                                 {"device_tag": "critical", "digital_output": "critical",
                                  "line_numbering": "minor", "description": "major"})
    eq(res["correction_count"], 0, "the --K66901 -> -K66901 device_tag change is noise, not a correction")
    eq(len(res["noise"]), 1, "it lands in the AREA noise listing")
    eq(res["by_tier"]["critical"], 1, "counts unchanged - the row is still counted at its tier")
    eq(res["moved"], 1, "the per-row move is still recorded (safety-critical, not suppressed)")


def test_area_real_device_tag_change_stays():
    # a genuine device_tag change (2 alnum chars differ) is NOT noise -> stays an AREA correction.
    old = {"_sheet": "AREA 1", "device_tag": "=S1+UL1.CC1-K66901", "digital_output": "Q640.0",
           "line_numbering": "L1", "description": "BELT"}
    new = {"_sheet": "AREA 1", "device_tag": "=S1+UL1.CC1-K77902", "digital_output": "Q640.0",
           "line_numbering": "L1", "description": "BELT"}
    mr = {"pairs": [{"old": old, "new": new, "moved": False}], "removed": [], "added": []}
    res = classify.classify_area(mr, {"AREA 1": 1}, {"AREA 1": 1}, {"device_tag": "critical"})
    eq(res["correction_count"], 1, "a real device_tag rename stays a correction")
    eq(len(res["noise"]), 0, "and is NOT classed as noise")


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
    ("address_grouped_not_hidden", test_address_grouped_not_hidden),
    ("direction_and_regression", test_direction_and_regression),
    ("upgrade_node_aware", test_upgrade_node_aware),
    ("channel_block_aggregation", test_channel_block_aggregation),
    ("render_html_smoke", test_render_html_smoke),
    ("no_previous_revision", test_no_previous_revision),
    ("t5_blank_never_hides_added", test_t5_blank_never_hides_added),
    ("subthreshold_rename_is_genuine", test_subthreshold_rename_is_genuine),
    ("unknown_tier_does_not_crash", test_unknown_tier_does_not_crash),
    ("empty_read_not_green", test_empty_read_not_green),
    ("address_decompose", test_address_decompose),
    ("address_lines_classify", test_address_lines_classify),
    ("fld_noise_predicate", test_fld_noise_predicate),
    ("fld_noise_category", test_fld_noise_category),
    ("by_nature_partitions_changed", test_by_nature_partitions_changed),
    ("struck_rows_counted", test_struck_rows_counted),
    ("area_multi_area_device_not_moved", test_area_multi_area_device_not_moved),
    ("area_genuine_move_detected", test_area_genuine_move_detected),
    ("area_membership_extended_and_moved", test_area_membership_extended_and_moved),
    ("area_device_tag_noise", test_area_device_tag_noise),
    ("area_real_device_tag_change_stays", test_area_real_device_tag_change_stays),
    ("read_error_degrades", test_read_error_degrades),
]

if __name__ == "__main__":
    import sys
    sys.exit(run("changes (ph100 before/after report)", TESTS))
