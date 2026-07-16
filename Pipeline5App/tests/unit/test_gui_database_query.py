"""GUI M3 - the Database Explorer engine (gui/dbquery.py): load the SSOT CSVs into in-memory SQLite and run
SQL (SELECT *, json_extract over a JSON cell, GROUP BY, a cross-table JOIN). Tk-free + hermetic (a temp
Database dir of CSVs in the real codec format)."""
import csv
import os
import tempfile

from _harness import run, eq, ok
from pipeline5.gui import database_query as dbquery


def _csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as h:
        w = csv.writer(h)
        w.writerow(header)
        w.writerows(rows)


def _fixture(d):
    # signals: a JSON `type` cell + a `datablocks` JSON-list cell (as core.table writes them)
    _csv(os.path.join(d, "signals.csv"),
         ["uid", "combined_FLD", "script_type", "type", "datablocks"],
         [["u1", "S1", "KQ", '{"type_id":"KQ"}', '["03_FDBACK"]'],
          ["u2", "S2", "KI", '{"type_id":"KI"}', "[]"],
          ["u3", "S3", "KQ", '{"type_id":"KQ"}', '["03_FDBACK"]']])
    _csv(os.path.join(d, "db_members.csv"),
         ["uid", "db_name", "member", "source"],
         [["m1", "03_FDBACK", "S1", "u1"], ["m2", "03_FDBACK", "S3", "u3"]])


def test_build_and_select():
    with tempfile.TemporaryDirectory() as d:
        _fixture(d)
        conn, schema = dbquery.build_memory_db(d)
        eq(set(schema), {"signals", "db_members"}, "one sqlite table per CSV")
        eq(schema["signals"], ["uid", "combined_FLD", "script_type", "type", "datablocks"], "the columns")
        cols, rows = dbquery.run_query(conn, "SELECT uid FROM signals ORDER BY uid")
        eq(cols, ["uid"])
        eq([r[0] for r in rows], ["u1", "u2", "u3"])


def test_json_extract_and_group_by():
    with tempfile.TemporaryDirectory() as d:
        _fixture(d)
        conn, _ = dbquery.build_memory_db(d)
        cols, rows = dbquery.run_query(
            conn, "SELECT json_extract(type,'$.type_id') AS t, COUNT(*) AS n FROM signals GROUP BY t ORDER BY t")
        eq(cols, ["t", "n"])
        eq(rows, [("KI", 1), ("KQ", 2)], "json_extract over the JSON cell + GROUP BY")


def test_signals_in_no_db_and_join():
    with tempfile.TemporaryDirectory() as d:
        _fixture(d)
        conn, _ = dbquery.build_memory_db(d)
        _c, rows = dbquery.run_query(conn, "SELECT combined_FLD FROM signals WHERE datablocks = '[]'")
        eq([r[0] for r in rows], ["S2"], "the JSON-list-cell '[]' = in no data block")
        _c2, joined = dbquery.run_query(
            conn, "SELECT s.combined_FLD, m.db_name FROM signals s "
                  "JOIN db_members m ON m.source = s.uid ORDER BY s.combined_FLD")
        eq(joined, [("S1", "03_FDBACK"), ("S3", "03_FDBACK")], "a cross-table JOIN on the uid FK")


def test_ragged_row_lenient_and_query_error():
    with tempfile.TemporaryDirectory() as d:
        _csv(os.path.join(d, "t.csv"), ["a", "b"], [["1", "2"], ["3"], ["5", "6", "7"]])  # ragged
        conn, _ = dbquery.build_memory_db(d)
        _c, rows = dbquery.run_query(conn, "SELECT a, b FROM t ORDER BY a")
        eq(rows, [("1", "2"), ("3", ""), ("5", "6")], "ragged rows padded/truncated to the header")
        import sqlite3
        try:
            dbquery.run_query(conn, "SELECT * FROM nope")
            ok(False, "a bad query should raise")
        except sqlite3.Error:
            ok(True, "sqlite3.Error on a bad query")


def test_dir_stamp_tracks_changes():
    with tempfile.TemporaryDirectory() as d:
        _fixture(d)
        s1 = dbquery.dir_stamp(d)
        eq(s1, dbquery.dir_stamp(d), "unchanged folder -> equal stamps (the rebuild is skipped)")
        with open(os.path.join(d, "signals.csv"), "a", newline="", encoding="utf-8") as h:
            h.write("u4,S4,KQ,{},[]\r\n")
        ok(dbquery.dir_stamp(d) != s1, "an appended row changes the stamp (size)")
        s2 = dbquery.dir_stamp(d)
        _csv(os.path.join(d, "extra.csv"), ["a"], [["1"]])
        ok(dbquery.dir_stamp(d) != s2, "a new table changes the stamp")


def test_connection_usable_across_threads():
    # The explorer BUILDS on a worker thread and QUERIES on the Tk thread - the connection must allow it.
    import threading
    with tempfile.TemporaryDirectory() as d:
        _fixture(d)
        box = {}
        t = threading.Thread(target=lambda: box.update(zip(("conn", "schema"), dbquery.build_memory_db(d))))
        t.start()
        t.join()
        _c, rows = dbquery.run_query(box["conn"], "SELECT COUNT(*) FROM signals")
        eq(rows[0][0], 3, "a connection built on another thread answers on this one")


if __name__ == "__main__":
    import sys
    sys.exit(run("gui_dbquery", [
        ("build_and_select", test_build_and_select),
        ("json_extract_and_group_by", test_json_extract_and_group_by),
        ("signals_in_no_db_and_join", test_signals_in_no_db_and_join),
        ("ragged_row_lenient_and_query_error", test_ragged_row_lenient_and_query_error),
        ("dir_stamp_tracks_changes", test_dir_stamp_tracks_changes),
        ("connection_usable_across_threads", test_connection_usable_across_threads),
    ]))
