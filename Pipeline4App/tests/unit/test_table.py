"""The JSON-cell table (core.table.Table): keying, round-trip fidelity, query, schema-leniency."""
import os
import tempfile

from _harness import run, eq, ok, raises
from pipeline4.core.keys import uid
from pipeline4.core.table import Table, encode_cell


def _signals_table():
    return Table(
        "signals",
        columns=["uid", "combined_FLD", "script_type", "datablocks", "matrix_areas", "type"],
        json_columns=["datablocks", "matrix_areas", "type"],
        key_columns=["combined_FLD", "script_type"],
    )


def test_add_stamps_uid_from_key_columns():
    t = _signals_table()
    r = t.add(combined_FLD="=S1+SG1-B1", script_type="DI1/2", datablocks=["07_DOOR"], matrix_areas=["AREA 1"])
    eq(r["uid"], uid("=S1+SG1-B1", "DI1/2"), "uid = content hash of the key columns")


def test_supplied_uid_is_not_overwritten():
    t = _signals_table()
    r = t.add(uid="fixed", combined_FLD="X", script_type="Y")
    eq(r["uid"], "fixed", "an explicit uid wins (e.g. a row carried over from disk)")


def test_json_cells_round_trip_exactly():
    t = _signals_table()
    t.add(combined_FLD="=S1-A,1", script_type="PA",                 # a comma inside a PLAIN cell
          datablocks=["PROFINET_NODES_ALARM", "00_Commissioning"],
          matrix_areas=[],                                          # empty list, NOT None
          type={"type_id": "PA", "db_names": ["X", "Y"], "in_diagnosis": True, "note": 'a "quoted", value'})
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "signals.csv")
        t.write_csv(path)
        loaded = _signals_table().read_csv(path)
    eq(len(loaded.rows), 1)
    r = loaded.rows[0]
    eq(r["datablocks"], ["PROFINET_NODES_ALARM", "00_Commissioning"], "list round-trips, order preserved")
    eq(r["matrix_areas"], [], "empty list stays [] (distinct from None)")
    eq(r["type"]["db_names"], ["X", "Y"], "a nested list inside an object round-trips")
    eq(r["type"]["in_diagnosis"], True, "a bool keeps its type")
    eq(r["type"]["note"], 'a "quoted", value', "quotes + commas inside JSON survive CSV quoting")
    eq(r["combined_FLD"], "=S1-A,1", "a plain cell containing a comma survives")


def test_none_json_cell_round_trips_as_none():
    t = _signals_table()
    t.add(combined_FLD="=S1-X", script_type="X", datablocks=None)  # an absent list
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "s.csv")
        t.write_csv(path)
        r = _signals_table().read_csv(path).rows[0]
    eq(r["datablocks"], None, "None json cell -> empty cell -> None (not '' or [])")


def test_deterministic_object_encoding():
    # dict key order must NOT affect the stored bytes (so tables diff cleanly + parity is stable)
    a = Table("t", ["o"], json_columns=["o"]); a.add(o={"b": 1, "a": 2})
    b = Table("t", ["o"], json_columns=["o"]); b.add(o={"a": 2, "b": 1})
    with tempfile.TemporaryDirectory() as d:
        pa, pb = os.path.join(d, "a.csv"), os.path.join(d, "b.csv")
        a.write_csv(pa); b.write_csv(pb)
        eq(open(pa, "rb").read(), open(pb, "rb").read(), "key order does not change the bytes")


def test_query_helpers():
    t = _signals_table()
    t.add(combined_FLD="A", script_type="DI1/2", datablocks=["07_DOOR"])
    t.add(combined_FLD="B", script_type="PA", datablocks=["PROFINET_NODES_ALARM"])
    eq(len(t.where(lambda r: r["script_type"] == "PA")), 1, "where filters")
    eq(t.first(lambda r: r["combined_FLD"] == "A")["script_type"], "DI1/2", "first finds")
    ok(t.by_uid(t.rows[0]["uid"]) is t.rows[0], "by_uid returns the row object")
    ok(t.by_uid("nope") is None, "by_uid miss -> None")


def test_undeclared_columns_are_preserved():
    t = Table("t", columns=["uid", "a"], json_columns=[])
    t.add(uid="x1", a="1", surprise="kept")            # a key outside the declared columns
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "t.csv")
        t.write_csv(path)
        r = Table("t", columns=["uid", "a"]).read_csv(path).rows[0]
    eq(r.get("surprise"), "kept", "an undeclared column is written + read, not silently dropped")


def test_extra_columns_sorted_deterministically():
    # the extra-column tail must produce the SAME header regardless of add-order / dict-key order (parity)
    def _header(rows):
        t = Table("t", ["uid"], json_columns=[])
        t.extend(rows)
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.csv")
            t.write_csv(p)
            return open(p, encoding="utf-8").readline().strip()
    a = _header([{"uid": "a", "x": "1"}, {"uid": "b", "y": "2"}])
    b = _header([{"uid": "b", "y": "2"}, {"uid": "a", "x": "1"}])
    eq(a, "uid,x,y", "extras sorted into the header")
    eq(a, b, "same header regardless of row/key order")


def test_write_rejects_structured_value_in_plain_column():
    t = Table("t", ["uid", "a"], json_columns=[])
    t.add(uid="x", a=["should", "be", "declared", "json"])
    with tempfile.TemporaryDirectory() as d:
        raises(ValueError, lambda: t.write_csv(os.path.join(d, "t.csv")))


def test_read_locates_a_bad_json_cell():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "t.csv")
        open(p, "w", newline="", encoding="utf-8").write("uid,payload\r\nx,notjson\r\n")
        try:
            Table("sig", ["uid", "payload"], json_columns=["payload"]).read_csv(p)
            ok(False, "should have raised")
        except ValueError as e:
            ok("payload" in str(e) and "row 0" in str(e), "the error names the column + row")


def test_read_rejects_ragged_row_and_duplicate_header():
    with tempfile.TemporaryDirectory() as d:
        ragged = os.path.join(d, "r.csv"); open(ragged, "w", newline="", encoding="utf-8").write("a,b,c\r\n1\r\n")
        raises(ValueError, lambda: Table("r", ["a", "b", "c"]).read_csv(ragged))
        dup = os.path.join(d, "d.csv"); open(dup, "w", newline="", encoding="utf-8").write("a,a\r\n1,2\r\n")
        raises(ValueError, lambda: Table("d", ["a"]).read_csv(dup))


def test_iter_len_extend():
    t = Table("t", ["uid", "v"], key_columns=["v"])
    t.extend([{"v": "1"}, {"v": "2"}])
    eq(len(t), 2, "__len__")
    eq([r["v"] for r in t], ["1", "2"], "__iter__ in row order")


def test_duplicate_uids_detector():
    t = Table("t", ["uid", "fld", "st"], key_columns=["fld", "st"])
    t.add(fld="X", st="DI1/2"); t.add(fld="X", st="DI1/2"); t.add(fld="Y", st="PA")
    eq(t.duplicate_uids(), {uid("X", "DI1/2")}, "two entities hashing equal are reported")


def test_encode_rejects_non_finite_float():
    raises(ValueError, lambda: encode_cell(float("nan")))
    raises(ValueError, lambda: encode_cell([float("inf")]))


if __name__ == "__main__":
    import sys
    sys.exit(run("table", [
        ("add_stamps_uid_from_key_columns", test_add_stamps_uid_from_key_columns),
        ("supplied_uid_is_not_overwritten", test_supplied_uid_is_not_overwritten),
        ("json_cells_round_trip_exactly", test_json_cells_round_trip_exactly),
        ("none_json_cell_round_trips_as_none", test_none_json_cell_round_trips_as_none),
        ("deterministic_object_encoding", test_deterministic_object_encoding),
        ("query_helpers", test_query_helpers),
        ("undeclared_columns_are_preserved", test_undeclared_columns_are_preserved),
        ("extra_columns_sorted_deterministically", test_extra_columns_sorted_deterministically),
        ("write_rejects_structured_value_in_plain_column", test_write_rejects_structured_value_in_plain_column),
        ("read_locates_a_bad_json_cell", test_read_locates_a_bad_json_cell),
        ("read_rejects_ragged_row_and_duplicate_header", test_read_rejects_ragged_row_and_duplicate_header),
        ("iter_len_extend", test_iter_len_extend),
        ("duplicate_uids_detector", test_duplicate_uids_detector),
        ("encode_rejects_non_finite_float", test_encode_rejects_non_finite_float),
    ]))
