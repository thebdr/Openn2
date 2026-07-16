"""ph200 device-tag RANGE notation: trailing-digit expansion, the channel `<n>/<N>` script_type suffix
(a multi-channel family authored as independent component rows), and range-aware index grouping."""
from _harness import run, eq, ok
from pipeline5.phases.fillout import device_tag_ranges as ranges
from pipeline5.phases.fillout import script_type_classify as classify
from pipeline5.phases.fillout import index_assign
from pipeline5.phases.fillout.type_families import ObjectFamily, LINK_SERIES


def test_range_parts_and_expand():
    eq(ranges.range_parts("=S1+DL1.CC1-K66701..2"), ("=S1+DL1.CC1-K6670", 1, 2), "trailing-digit range parts")
    eq(ranges.range_parts("=S1+DL1.CC1-K66701"), None, "a plain FLD is not a range")
    eq(ranges.expand_range_fld("=S1-Q66403..4"), ["=S1-Q66403", "=S1-Q66404"], "expand 3..4 -> two components")
    eq(ranges.expand_range_fld("=S1-K66701"), ["=S1-K66701"], "a non-range FLD expands to itself")
    ok(ranges.is_range("-K66701..2") and not ranges.is_range("-K66701"), "is_range on the device form")


def test_build_channel_map():
    m = ranges.build_channel_map(["=S1-K66701..2", "=S1-K66701", "=S1-Q66403..4"])
    eq(m.get("=S1-K66701"), (1, 2), "K66701..2 component 1 of 2")
    eq(m.get("=S1-K66702"), (2, 2), "K66701..2 component 2 of 2")
    eq(m.get("=S1-Q66403"), (1, 2), "Q66403..4 component 1 of 2 (position L->R, not the absolute digit)")
    eq(m.get("=S1-Q66404"), (2, 2), "Q66403..4 component 2 of 2")


# a contactor family (K series, KQ anchor) for the suffix + index tests
_K = ObjectFamily(family="contactor", key="K", member_types=("KI", "KQ"), anchor="KQ",
                  link=LINK_SERIES, index_stride=1, bits=1, diag_block="")


def _row(uid, dev, st, ch="", row=0):
    return {"uid": uid, "functional_unit": "=S1", "location": "+DL1.CC1", "device": dev, "script_type": st,
            "index": "", "source_sheet": "S", "source_row": row,
            "type": {"channel": ch, "category": "Safety", "type_id": st} if ch or st else None}


def test_channel_suffix_components():
    sig = {"KI": {}, "KI1/2": {}, "KI2/2": {}, "KQ": {}}                  # the valid signal_types set
    rows = [_row("a1", "-K66701..2", "KQ"), _row("a2", "-K66701", "KI"), _row("a3", "-K66702", "KI")]
    base = {"a1": "KQ", "a2": "KI", "a3": "KI"}
    suffixed, invalid = classify.channel_suffixes(rows, [_K], sig, base)
    eq(suffixed.get("a2"), "KI1/2", "independent component 1 -> KI1/2")
    eq(suffixed.get("a3"), "KI2/2", "independent component 2 -> KI2/2")
    ok("a1" not in suffixed, "the range row itself keeps its base type (KQ)")
    eq(invalid, [], "every derived type is a known signal_type")


def test_channel_suffix_unknown_type_marked():
    sig = {"KI": {}, "KI1/2": {}, "KI2/2": {}}                            # NO KI1/5.. (coverage stops short)
    rows = [_row("b1", "-K66701..5", "KQ"), _row("b2", "-K66701", "KI")]
    base = {"b1": "KQ", "b2": "KI"}
    suffixed, invalid = classify.channel_suffixes(rows, [_K], sig, base)
    eq(suffixed.get("b2"), "<KI1/5>", "an unknown derived type is written MARKED <KI1/5>")
    eq(len(invalid), 1, "the unknown derived type is reported")
    eq(invalid[0][1], "KI1/5", "the reported (plain) candidate")
    eq(classify.unmark("<KI1/5>"), "KI1/5", "unmark strips the marker")


def test_index_range_aware_inherit():
    # the independent KI components inherit the KQ RANGE anchor's index (range-aware fld_anchor match)
    rows = [_row("k1", "-K66701..2", "KQ", "", 1),
            _row("k2", "-K66701", "KI1/2", "1", 2),
            _row("k3", "-K66702", "KI2/2", "2", 3)]
    idx = index_assign.assign_indices(rows, [_K], from_scratch=True)
    ok(idx["k1"] and idx["k1"] != "<input required>", "the KQ range anchor gets a real index")
    eq(idx["k2"], idx["k1"], "KI1/2 (independent component) inherits the KQ range anchor index")
    eq(idx["k3"], idx["k1"], "KI2/2 inherits the same index (the whole contactor is one object)")


if __name__ == "__main__":
    import sys
    sys.exit(run("fillout_ranges", [
        ("range_parts_and_expand", test_range_parts_and_expand),
        ("build_channel_map", test_build_channel_map),
        ("channel_suffix_components", test_channel_suffix_components),
        ("channel_suffix_unknown_type_marked", test_channel_suffix_unknown_type_marked),
        ("index_range_aware_inherit", test_index_range_aware_inherit),
    ]))
