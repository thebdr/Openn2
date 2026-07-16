"""ph200 / 220 INDEX assignment (object grouping) - hermetic, synthetic staged signal dicts.

Covers: family_for LONGEST-prefix (DI beats D); role_of for each link kind; the channel-2 FLD inherit;
the KQ/KI series (primary inherit + sibling contiguity + ki_without_kq); a standalone A/W counter; the
pattern (Z) shared index; an unresolved (channel_fld_mismatch) -> "<input required>". A faithful clean-
room port verification of PL3's index_assign over PL4's signals-dict model.
"""
from _harness import run, eq
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


if __name__ == "__main__":
    import sys
    sys.exit(run("fillout_index", [
        ("family_for_longest_prefix", test_family_for_longest_prefix),
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
