"""Phase 510 - the PLCTags.xlsx projection (domain.io_tags): the two SSOT sources (resolved I/O signals
+ the interface_elements), the data-type map, the %-address, the text-forcing, the two-sheet structure.
Hermetic: a synthetic Database in-memory, projected to a temp dir, re-opened + asserted."""
import os
import tempfile

from openpyxl import load_workbook

from _harness import run, eq, ok
from pipeline4.core.database import Database
from pipeline4.domain import io_tags, interfaces
from pipeline4.domain.signals import signals_table

_IOLIST = ["functional_unit", "location", "device", "script_type", "bit"]


def _db(signals=(), elements=()):
    sig = signals_table(_IOLIST)
    for s in signals:
        sig.add(**s)
    el = interfaces.interface_elements_table()
    for e in elements:
        el.add(**e)
    return Database([sig, el])


def _project(signals=(), elements=()):
    db = _db(signals, elements)
    with tempfile.TemporaryDirectory() as d:
        res = io_tags.project(db, out_dir=d)
        wb = load_workbook(res["path"])
        tags = wb["PLC Tags"]
        rows = [[c.value for c in tags[r]] for r in range(1, tags.max_row + 1)]
        props = wb["TagTable Properties"]
        prows = [[c.value for c in props[r]] for r in range(1, props.max_row + 1)]
        wb.close()
    return res, rows, prows


def test_tia_dtype_and_logical_address():
    eq(io_tags._tia_dtype("bool"), "Bool")
    eq(io_tags._tia_dtype("WORD"), "Word")
    eq(io_tags._tia_dtype(""), "Bool", "blank -> Bool default")
    eq(io_tags._tia_dtype("foo"), "Foo", "unknown type capitalizes")
    eq(io_tags._logical_address("I1.0"), "%I1.0")
    eq(io_tags._logical_address("%Q10000.0"), "%Q10000.0", "already %-prefixed -> unchanged")
    eq(io_tags._logical_address(""), "")
    eq(io_tags._logical_address(None), "")


def test_two_sheet_structure_and_headers():
    _res, rows, prows = _project()
    eq(rows[0], io_tags.TAG_COLUMNS, "PLC Tags header = the 10 columns in order")
    eq(prows[0], io_tags.PROP_COLUMNS, "TagTable Properties header = the 3 columns")


def test_source_a_direct_io_signal():
    sig = {"script_type": "DI1/2", "bit": "I1.0", "name_in_tagtable": "PB START",
           "tagtable": "EMERGENCY_PushButtons",
           "type": {"type_id": "DI1/2", "category": "Safety", "io_comment": "[ {$script_type} ]"}}
    _res, rows, _p = _project(signals=[sig])
    eq(rows[1], ["PB START", "EMERGENCY_PushButtons", "Bool", "%I1.0", "[ DI1/2 ]",
                 "True", "True", "True", None, None],
       "the direct-I/O tag row (Bool, %-addr, resolved comment; empty Typeobject/Version read as None)")


def test_source_a_skips_blank_and_non_io():
    sigs = [
        {"script_type": "DI1/2", "bit": "I1.0", "name_in_tagtable": "",            # blank name -> skip
         "type": {"category": "Safety"}},
        {"script_type": "IOC", "bit": "I2.0", "name_in_tagtable": "X",             # Interface category -> not is_io
         "type": {"category": "Interface"}},
        {"script_type": "STD", "bit": "", "name_in_tagtable": "Y",                 # no I/Q bit -> not is_io
         "type": {"category": "Std"}},
    ]
    res, rows, _p = _project(signals=sigs)
    eq(res["io_count"], 0, "none of the three is a taggable I/O signal")
    eq(len(rows), 1, "only the header row")


def test_source_b_interface_tag_from_ssot():
    el = {"interface": "SORTER-01", "signal_name": "PNC_Q_Breaker", "data_type": "BOOL",
          "direction": "Q", "io_address_side1": "Q10000.0", "description": "breaker"}
    res, rows, prows = _project(elements=[el])
    eq(res["iface_count"], 1)
    eq(rows[1], ["PNC_Q_Breaker", "IF_SORTER-01", "Bool", "%Q10000.0", "breaker",
                 "True", "True", "True", None, None], "interface tag: Path=IF_<inst>, stored addr %-prefixed")
    eq(prows[1], ["IF_SORTER-01", None, None], "the IF_ table appears in TagTable Properties")


def test_source_b_word_and_unresolved():
    els = [
        {"interface": "S-01", "signal_name": "SPD", "data_type": "WORD", "direction": "Q",
         "io_address_side1": "Q10026", "description": "speed"},
        {"interface": "S-01", "signal_name": "NOADDR", "data_type": "BOOL", "direction": "Q",
         "io_address_side1": "", "description": "missing"},            # no resolved address -> skip + warn
    ]
    res, rows, _p = _project(elements=els)
    eq(res["iface_count"], 1, "the WORD tag is emitted; the address-less one is skipped")
    eq(rows[1][2], "Word", "WORD -> Word")
    eq(rows[1][3], "%Q10026", "WORD address has no bit")
    ok(any(f.type == "iotag_no_address" and "NOADDR" in f.location and f.severity == "WARN"
           for f in res["findings"]),
       "the unresolved-address element is a iotag_no_address WARN finding")


def test_text_forcing_and_sort_and_props():
    # two tables (sorted), a Name starting with '=' must stay TEXT (data_type 's'), distinct props
    sigs = [
        {"script_type": "ZZ", "bit": "Q5.0", "name_in_tagtable": "=S1+MS1-F1", "tagtable": "Zlast",
         "type": {"category": "Std", "io_comment": ""}},
        {"script_type": "AA", "bit": "I0.0", "name_in_tagtable": "alpha", "tagtable": "Afirst",
         "type": {"category": "Std", "io_comment": ""}},
        {"script_type": "AA", "bit": "I0.1", "name_in_tagtable": "beta", "tagtable": "Afirst",
         "type": {"category": "Std", "io_comment": ""}},
    ]
    res, rows, prows = _project(signals=sigs)
    eq([r[1] for r in rows[1:]], ["Afirst", "Afirst", "Zlast"], "rows grouped + sorted by Path")
    eq([r[0] for r in rows[1:]], ["alpha", "beta", "=S1+MS1-F1"], "insertion order within a table")
    eq([p[0] for p in prows[1:]], ["Afirst", "Zlast"], "distinct tables, sorted")
    with tempfile.TemporaryDirectory() as d:
        path = io_tags.project(_db(signals=sigs), out_dir=d)["path"]
        ws = load_workbook(path)["PLC Tags"]
        # the '=' Name is on the Zlast row (row 4); it must be stored as a string, not a formula
        cell = next(c for row in ws.iter_rows() for c in row if c.value == "=S1+MS1-F1")
        eq(cell.data_type, "s", "a leading '=' Name is forced to text, not a formula")


def test_return_contract_mixes_sources():
    sigs = [{"script_type": "DI1/2", "bit": "I1.0", "name_in_tagtable": "PB",
             "type": {"category": "Safety", "io_comment": ""}}]
    els = [{"interface": "S-01", "signal_name": "PNC", "data_type": "BOOL", "direction": "Q",
            "io_address_side1": "Q10000.0", "description": ""}]
    res, _rows, _p = _project(signals=sigs, elements=els)
    eq((res["io_count"], res["iface_count"], res["total"]), (1, 1, 2), "io + iface == total")
    ok(res["path"].endswith("PLCTags.xlsx"), "writes PLCTags.xlsx")


if __name__ == "__main__":
    import sys
    sys.exit(run("io_tags", [
        ("tia_dtype_and_logical_address", test_tia_dtype_and_logical_address),
        ("two_sheet_structure_and_headers", test_two_sheet_structure_and_headers),
        ("source_a_direct_io_signal", test_source_a_direct_io_signal),
        ("source_a_skips_blank_and_non_io", test_source_a_skips_blank_and_non_io),
        ("source_b_interface_tag_from_ssot", test_source_b_interface_tag_from_ssot),
        ("source_b_word_and_unresolved", test_source_b_word_and_unresolved),
        ("text_forcing_and_sort_and_props", test_text_forcing_and_sort_and_props),
        ("return_contract_mixes_sources", test_return_contract_mixes_sources),
    ]))
