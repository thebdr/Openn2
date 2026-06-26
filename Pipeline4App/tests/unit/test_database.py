"""The Database (core.database.Database): multi-table save/load round-trip + access forms."""
import os
import tempfile

from _harness import run, eq, ok, raises
from pipeline4.core.database import Database
from pipeline4.core.table import Table


def _database():
    return Database([
        Table("signals", ["uid", "combined_FLD", "datablocks"],
              json_columns=["datablocks"], key_columns=["combined_FLD"]),
        Table("db_members", ["uid", "db_name", "member", "source_uid"],
              json_columns=[], key_columns=["db_name", "member"]),
    ])


def test_save_load_round_trip_with_foreign_key():
    db = _database()
    signal = db["signals"].add(combined_FLD="=S1+SG1-B1", datablocks=["07_DOOR"])
    db["db_members"].add(db_name="07_DOOR", member="Door Closed", source_uid=signal["uid"])
    with tempfile.TemporaryDirectory() as d:
        db.save(d)
        ok(os.path.exists(os.path.join(d, "signals.csv")), "signals table written")
        ok(os.path.exists(os.path.join(d, "db_members.csv")), "db_members table written")
        fresh = _database().load(d)
    eq(fresh["signals"].rows[0]["datablocks"], ["07_DOOR"], "signals round-trips typed (list cell)")
    eq(fresh["db_members"].rows[0]["source_uid"], signal["uid"],
       "the FK from db_members back to the signal's uid survives the round-trip")


def test_load_missing_table_is_noop():
    with tempfile.TemporaryDirectory() as d:
        seed = _database()
        seed["signals"].add(combined_FLD="X")
        seed["signals"].write_csv(os.path.join(d, "signals.csv"))   # only signals on disk
        fresh = _database().load(d)
    eq(len(fresh["signals"].rows), 1, "the present table is loaded")
    eq(len(fresh["db_members"].rows), 0, "an absent table file -> empty table, no error")


def test_access_forms():
    db = _database()
    ok(db.table("signals") is db["signals"], "table() and [] return the same object")
    ok("signals" in db and "nope" not in db, "__contains__")
    eq(sorted(db.names()), ["db_members", "signals"], "names()")


def test_duplicate_table_name_rejected():
    raises(ValueError, lambda: Database([Table("x", ["uid"]), Table("x", ["uid"])]))


if __name__ == "__main__":
    import sys
    sys.exit(run("database", [
        ("save_load_round_trip_with_foreign_key", test_save_load_round_trip_with_foreign_key),
        ("load_missing_table_is_noop", test_load_missing_table_is_noop),
        ("access_forms", test_access_forms),
        ("duplicate_table_name_rejected", test_duplicate_table_name_rejected),
    ]))
