"""ph200 / 220 INDEX assignment (object grouping) - hermetic, synthetic staged signal dicts.

Covers: family_for LONGEST-prefix (DI beats D); role_of for each link kind; the channel-2 FLD inherit;
the KQ/KI series (primary inherit + sibling contiguity + ki_without_kq); a standalone A/W counter; the
pattern (Z) shared index; an unresolved (channel_fld_mismatch) -> "<input required>". A faithful clean-
room port verification of PL3's index_assign over PL4's signals-dict model.
"""
from _harness import run, eq, ok
from pipeline5.phases.fillout import index_assign as ix
from pipeline5.phases.fillout import type_families as fam
from pipeline5.phases.fillout.type_families import (
    ObjectFamily, LINK_CHANNEL, LINK_SERIES, LINK_FLD, LINK_PATTERN, LINK_NONE,
)

INPUT_REQUIRED = "<input required>"

# A synthetic family table covering every link kind (mirrors object_families.csv structure).
_FAMS = [
    ObjectFamily("door", "D", ("DI", "DD", "DR", "DL", "DQ", "DO"), "DI1/2", LINK_FLD, 1, 2, "+SafetyDoors"),
    ObjectFamily("contactor", "K", ("KI", "KQ"), "KQ", LINK_SERIES, 1, 1, ""),
    ObjectFamily("emergency_pb", "E", ("E1/2", "E2/2"), "E1/2", LINK_CHANNEL, 1, 1, "+EPB"),
    ObjectFamily("reset", "R", ("R*", "R#"), "R*", LINK_NONE, 1, 0, ""),
    ObjectFamily("emergency_area", "Z", ("Z#",), "Z#", LINK_PATTERN, 1, 1, "+EA"),
]


def _row(uid, script_type, *, fld="", source_row=0, channel="", category="", index="", type_present=True):
    """A synthetic STAGED signals dict (only the fields index_assign reads)."""
    fu = fld
    type_def = None
    if type_present:
        type_def = {"category": category, "channel": channel}
    return {
        "uid": uid, "script_type": script_type, "type": type_def,
        "functional_unit": fu, "location": "", "device": "",
        "source_row": source_row, "index": index,
    }


def _res(row):
    return ix._Res(row, _FAMS, row.get("index") or "")


# --- family_for ---------------------------------------------------------------------------------- #
def test_family_for_longest_prefix():
    di = fam.family_for("DI1/2", _FAMS)
    d = fam.family_for("DD", _FAMS)
    eq(di.key, "D", "DI1/2 -> door (key D)")
    eq(d.key, "D", "DD -> door (key D)")
    # DI must win 'D' (longest prefix) even though both share key 'D' here; verify against a real
    # two-key table where DI is its own key.
    fams2 = list(_FAMS) + [ObjectFamily("dx", "DI", (), "", LINK_CHANNEL, 1, 0, "")]
    eq(fam.family_for("DI1/2", fams2).key, "DI", "DI beats D (longest-prefix)")
    eq(fam.family_for("DD", fams2).key, "D", "DD still -> D")
    eq(fam.family_for("A", _FAMS), None, "A is not a family")
    eq(fam.family_for("", _FAMS), None, "blank -> None")


def test_shipped_el_joins_emergency_pb():
    """C-027 + C-029: the SHIPPED object_families. A single-row e-stop (E - both channels on one row, checked in
    hardware) is complete by itself; a two-row e-stop (E1/2) still needs its E2/2. The lamp (EL) is a FOLLOWER:
    it takes the index of the e-stop with its designation but is never that e-stop's partner - a lamp does not
    complete a two-row e-stop missing its CH2 (C-027 refute round 1). A lamp with no e-stop stays unresolved."""
    shipped = fam.load_object_families()
    el = fam.family_for("EL", shipped)
    eq((el.key, el.link), ("E", LINK_CHANNEL), "EL -> the emergency_pb family (channel link)")
    eq(ix.role_of(ix._Res(_row("u", "E"), shipped, "")), ix.SINGLE, "E (an anchor type, no channel) -> single")
    eq(ix.role_of(ix._Res(_row("u", "EL"), shipped, "")), ix.FOLLOWER, "EL (not an anchor, no channel) -> follower")
    eq(ix.role_of(ix._Res(_row("u", "E1/2", channel="1"), shipped, "")), ix.ANCHOR, "E1/2 stays the paired anchor")
    rows = [_row("e1", "E1/2", fld="=ES-1", channel="1", source_row=1),
            _row("f1", "E2/2", fld="=ES-1", channel="2", source_row=2),
            _row("l1", "EL", fld="=ES-1", source_row=3),
            _row("s2", "E", fld="=ES-2", source_row=4),                 # one row, both channels + its lamp
            _row("l2", "EL", fld="=ES-2", source_row=5),
            _row("s3", "E", fld="=ES-3", source_row=6),                 # one row, no lamp
            _row("e4", "E1/2", fld="=ES-4", channel="1", source_row=7),  # CH1 + a lamp, CH2 missing
            _row("l4", "EL", fld="=ES-4", source_row=8),
            _row("l9", "EL", fld="=ES-9", source_row=9)]                # a lamp with no e-stop
    got = ix.assign_indices(rows, shipped)
    eq((got["e1"], got["f1"], got["l1"]), ("0001", "0001", "0001"), "the pair + its lamp share the index")
    eq((got["s2"], got["l2"]), ("0002", "0002"), "a single-row e-stop is complete; its lamp inherits")
    eq(got["s3"], "0003", "a single-row e-stop without a lamp is complete too")
    eq(got["e4"], INPUT_REQUIRED, "a lamp does NOT complete a two-row e-stop missing its CH2")
    eq(got["l4"], "0004", "that lamp still follows its e-stop's index")
    eq(got["l9"], INPUT_REQUIRED, "a lamp whose designation has no e-stop is unresolved")


# --- role_of for each link kind ------------------------------------------------------------------ #
def test_role_of_each_link():
    eq(ix.role_of(_res(_row("u", "E1/2", channel="1"))), ix.ANCHOR, "channel ch1 -> anchor")
    eq(ix.role_of(_res(_row("u", "E2/2", channel="2"))), ix.CHANNEL_2, "channel ch2 -> channel_2")
    eq(ix.role_of(_res(_row("u", "KQ"))), ix.ANCHOR, "KQ -> series anchor")
    eq(ix.role_of(_res(_row("u", "KI", channel="1"))), ix.SERIES_PRIMARY, "KI ch1 -> series_primary")
    eq(ix.role_of(_res(_row("u", "KI", channel="2"))), ix.SERIES_SIBLING, "KI ch2 -> series_sibling")
    eq(ix.role_of(_res(_row("u", "DI1/2", channel="1"))), ix.ANCHOR, "DI ch1 -> fld anchor")
    eq(ix.role_of(_res(_row("u", "DD"))), ix.FLD_INHERIT, "DD -> fld_inherit")
    eq(ix.role_of(_res(_row("u", "DI2/2", channel="2"))), ix.FLD_INHERIT, "DI ch2 -> fld_inherit")
    eq(ix.role_of(_res(_row("u", "DL"))), ix.MANUAL, "DL -> manual")
    eq(ix.role_of(_res(_row("u", "R*"))), ix.RESET, "R* (link none) -> reset")
    eq(ix.role_of(_res(_row("u", "Z1"))), ix.PATTERN, "Z (link pattern) -> pattern")
    eq(ix.role_of(_res(_row("u", "A", type_present=True, category=""))), ix.STANDALONE, "A -> standalone")


# --- channel-2 FLD inherit ----------------------------------------------------------------------- #
def test_channel2_fld_inherit():
    rows = [
        _row("a", "E1/2", fld="X", source_row=1, channel="1"),
        _row("b", "E2/2", fld="X", source_row=2, channel="2"),   # same FLD -> inherits
    ]
    got = ix.assign_indices(rows, _FAMS, from_scratch=True)
    eq(got["a"], "0001", "anchor takes 0001")
    eq(got["b"], "0001", "channel-2 inherits the anchor index by FLD")


def test_channel2_fld_mismatch_unresolved():
    rows = [
        _row("a", "E1/2", fld="X", source_row=1, channel="1"),
        _row("b", "E2/2", fld="Y", source_row=2, channel="2"),   # different FLD -> unresolved
    ]
    got = ix.assign_indices(rows, _FAMS, from_scratch=True)
    eq(got["a"], INPUT_REQUIRED, "anchor with no matching ch2 FLD -> unresolved (symmetric check)")
    eq(got["b"], INPUT_REQUIRED, "channel-2 with no anchor FLD -> <input required>")


# --- KQ/KI series -------------------------------------------------------------------------------- #
def test_series_primary_and_sibling_contiguity():
    rows = [
        _row("kq", "KQ", fld="F", source_row=10),
        _row("ki1", "KI1/2", fld="F", source_row=11, channel="1"),  # primary inherits KQ by FLD
        _row("ki2", "KI2/2", fld="F", source_row=12, channel="2"),  # sibling, contiguous + same total
    ]
    got = ix.assign_indices(rows, _FAMS, from_scratch=True)
    eq(got["kq"], "0001", "KQ anchor -> 0001")
    eq(got["ki1"], "0001", "KI primary inherits KQ by FLD")
    eq(got["ki2"], "0001", "KI sibling inherits (contiguous + same /total)")


def test_series_ki_without_kq():
    rows = [
        _row("ki1", "KI1/2", fld="NOPE", source_row=11, channel="1"),  # no KQ at this FLD
    ]
    got = ix.assign_indices(rows, _FAMS, from_scratch=True)
    eq(got["ki1"], INPUT_REQUIRED, "KI primary with no KQ FLD -> ki_without_kq")


def test_series_sibling_non_contiguous():
    rows = [
        _row("kq", "KQ", fld="F", source_row=10),
        _row("ki1", "KI1/2", fld="F", source_row=11, channel="1"),
        _row("ki2", "KI2/2", fld="F", source_row=20, channel="2"),  # row gap -> breaks contiguity
    ]
    got = ix.assign_indices(rows, _FAMS, from_scratch=True)
    eq(got["ki1"], "0001", "primary inherits")
    eq(got["ki2"], INPUT_REQUIRED, "non-contiguous sibling -> unresolved")


# --- standalone A/W counter ---------------------------------------------------------------------- #
def test_standalone_counter():
    rows = [
        _row("a1", "A", fld="P", source_row=1, category=""),
        _row("a2", "A", fld="Q", source_row=2, category=""),
        _row("w1", "W", fld="R", source_row=3, category=""),
    ]
    got = ix.assign_indices(rows, _FAMS, from_scratch=True)
    eq(got["a1"], "0001", "A standalone counter starts 0001")
    eq(got["a2"], "0002", "A counter increments (per script_type key)")
    eq(got["w1"], "0001", "W has its own standalone counter")


# --- pattern (Z) shared index -------------------------------------------------------------------- #
def test_pattern_shared_index():
    rows = [
        _row("z1", "Z1", fld="A", source_row=1),
        _row("z2", "Z2", fld="B", source_row=2),
    ]
    got = ix.assign_indices(rows, _FAMS, from_scratch=True)
    eq(got["z1"], "0001", "first Z takes the shared pattern index")
    eq(got["z2"], "0001", "every Z shares the one pattern index")


# --- idempotency (a digit ex_index is preserved) ------------------------------------------------- #
def test_idempotency_preserves_digit_index():
    # A MANUAL door member (DL) cannot auto-resolve; a genuine prior index is preserved.
    rows = [_row("dl", "DL", fld="Z", source_row=5, index="0007")]
    got = ix.assign_indices(rows, _FAMS, from_scratch=False)
    eq(got["dl"], "0007", "manual member with a digit ex_index -> preserved (not sentinel)")
    got_fs = ix.assign_indices(rows, _FAMS, from_scratch=True)
    eq(got_fs["dl"], INPUT_REQUIRED, "from scratch the same manual member is unresolved")


# --- is_indexable -------------------------------------------------------------------------------- #
def test_is_indexable():
    eq(ix.is_indexable(_res(_row("u", "A", category=""))), True, "typed non-interface -> indexable")
    eq(ix.is_indexable(_res(_row("u", "IOC", category="Interface"))), False, "interface -> not indexable")
    eq(ix.is_indexable(_res(_row("u", ""))), False, "no script_type -> not indexable")
    eq(ix.is_indexable(_res(_row("u", INPUT_REQUIRED))), False, "sentinel script_type -> not indexable")
    eq(ix.is_indexable(_res(_row("u", "DL", type_present=False))), True, "untyped but a family member -> indexable")


def test_shipped_e_matches_e12():
    """C-029 refute round 2: the SHIPPED type E gets everything an E1/2 gets - the e-stop tag table, the same
    rendered tag name, the C&E mandate, diagnosis (pressed / released) and interface tag name - and has NO
    channel, so a lone E typed from the shipped config is complete in the 200 index."""
    from pipeline5.config import paths, loaders
    from pipeline5.systems.plc_based.siemens_s7.safety.system import SYSTEM
    from pipeline5.truth import identity
    paths.use_system(SYSTEM)
    types = loaders.load_signal_types()
    e, pair = loaders.resolve_type(types, "E"), loaders.resolve_type(types, "E1/2")
    ok(e is not None, "E is a shipped type")
    eq(e.get("channel"), "", "one row - no channel")
    for k in ("category", "tagtable_name", "ce_mandatory", "io_comment"):
        eq(e.get(k), pair.get(k), f"E's {k} = E1/2's")
    row = {"combined_FLD": "=ES-1", "iol_FLD": "=ES-1"}
    eq(identity.tag_name(dict(row, script_type="E", type=e)),
       identity.tag_name(dict(row, script_type="E1/2", type=pair)), "the same tag name")
    diag = loaders.load_signal_diagnosis()
    ok(diag.get("E") and diag.get("E") == diag.get("E1/2"), "the same diagnosis (pressed / released)")
    names = loaders.load_interface_tagnames()
    ok(names.get("E") and names.get("E") == names.get("E1/2"), "the same interface tag name")
    lone = {"uid": "s", "script_type": "E", "type": e, "functional_unit": "=ES-1", "location": "", "device": "",
            "source_row": 1, "index": ""}
    eq(ix.assign_indices([lone], fam.load_object_families(), from_scratch=True)["s"], "0001",
       "a lone E typed from the shipped config is complete")


def test_single_with_channel_2_is_flagged():
    """C-029 refute round 2: an E2/2 on the designation of a ONE-row e-stop (E) is a contradiction - flagged
    (`<input required>`), never a silent inherit of the E's index; the E itself keeps its index."""
    shipped = fam.load_object_families()
    rows = [_row("s", "E", fld="=ES-5", source_row=1),
            _row("c", "E2/2", fld="=ES-5", channel="2", source_row=2)]
    got = ix.assign_indices(rows, shipped, from_scratch=True)
    eq((got["s"], got["c"]), ("0001", INPUT_REQUIRED), "the E2/2 beside an E is flagged")


def test_contradiction_reported_even_with_an_index():
    """C-029 refute round 3: in a NORMAL fill (existing indices kept) an E2/2 beside a one-row E that already
    carries an index - typed in, risky-filled, or from before the CH1 row became E - is STILL reported: its
    index is kept, the reason says the type is wrong."""
    shipped = fam.load_object_families()
    rows = [_row("s", "E", fld="=ES-5", source_row=1, index="0001"),
            _row("c", "E2/2", fld="=ES-5", channel="2", source_row=2, index="0001")]
    reasons = {}
    got = ix.assign_indices(rows, shipped, reasons=reasons)
    eq(got["c"], "0001", "the human index kept")
    eq(reasons, {"c": "single_with_channel_2"}, "the contradiction reported anyway")
    ok("not the index" in ix.CONTRADICTIONS["single_with_channel_2"], "the advice is the type, not the index")


def test_two_objects_on_one_designation_are_flagged():
    """C-029 refute round 3: a one-row E beside another E, or beside an E1/2 (whichever comes first), is a
    second object on one designation - flagged, never two indices / diag bits / channels."""
    shipped = fam.load_object_families()
    reasons = {}
    got = ix.assign_indices([_row("a", "E", fld="=ES-6", source_row=1),
                             _row("b", "E", fld="=ES-6", source_row=2)], shipped, from_scratch=True, reasons=reasons)
    eq((got["a"], got["b"], reasons), ("0001", INPUT_REQUIRED, {"b": "single_with_anchor"}), "E + E")
    reasons = {}
    got = ix.assign_indices([_row("p", "E1/2", fld="=ES-7", channel="1", source_row=1),
                             _row("s", "E", fld="=ES-7", source_row=2)], shipped, from_scratch=True, reasons=reasons)
    eq(reasons.get("s"), "single_with_anchor", "E1/2 then E")
    reasons = {}
    got = ix.assign_indices([_row("s", "E", fld="=ES-8", source_row=1),
                             _row("p", "E1/2", fld="=ES-8", channel="1", source_row=2),
                             _row("c", "E2/2", fld="=ES-8", channel="2", source_row=3)],
                            shipped, from_scratch=True, reasons=reasons)
    eq(reasons, {"p": "single_with_anchor", "c": "single_with_channel_2"}, "E then E1/2 + E2/2")


def test_contradictions_are_range_aware():
    """C-029 refute round 3: an E on one component of a device RANGE and an E1/2 + E2/2 pair authored on the
    range are the same designation - flagged; an E on a designation outside the range is not."""
    shipped = fam.load_object_families()
    reasons = {}
    ix.assign_indices([_row("s", "E", fld="=X-S1", source_row=1),
                       _row("p", "E1/2", fld="=X-S1..2", channel="1", source_row=2),
                       _row("c", "E2/2", fld="=X-S1..2", channel="2", source_row=3)],
                      shipped, from_scratch=True, reasons=reasons)
    eq(reasons, {"p": "single_with_anchor", "c": "single_with_channel_2"}, "the E sits on the range's component")
    reasons = {}
    got = ix.assign_indices([_row("s", "E", fld="=X-S9", source_row=1),
                             _row("p", "E1/2", fld="=X-S1..2", channel="1", source_row=2),
                             _row("c", "E2/2", fld="=X-S1..2", channel="2", source_row=3)],
                            shipped, from_scratch=True, reasons=reasons)
    eq((reasons, got["p"], got["c"]), ({}, "0002", "0002"), "outside the range: no contradiction")


if __name__ == "__main__":
    import sys
    sys.exit(run("fillout_index", [
        ("family_for_longest_prefix", test_family_for_longest_prefix),
        ("shipped_el_joins_emergency_pb", test_shipped_el_joins_emergency_pb),
        ("shipped_e_matches_e12", test_shipped_e_matches_e12),
        ("single_with_channel_2_is_flagged", test_single_with_channel_2_is_flagged),
        ("contradiction_reported_even_with_an_index", test_contradiction_reported_even_with_an_index),
        ("two_objects_on_one_designation_are_flagged", test_two_objects_on_one_designation_are_flagged),
        ("contradictions_are_range_aware", test_contradictions_are_range_aware),
        ("role_of_each_link", test_role_of_each_link),
        ("channel2_fld_inherit", test_channel2_fld_inherit),
        ("channel2_fld_mismatch_unresolved", test_channel2_fld_mismatch_unresolved),
        ("series_primary_and_sibling_contiguity", test_series_primary_and_sibling_contiguity),
        ("series_ki_without_kq", test_series_ki_without_kq),
        ("series_sibling_non_contiguous", test_series_sibling_non_contiguous),
        ("standalone_counter", test_standalone_counter),
        ("pattern_shared_index", test_pattern_shared_index),
        ("idempotency_preserves_digit_index", test_idempotency_preserves_digit_index),
        ("is_indexable", test_is_indexable),
    ]))
