"""The Database (core.database.Database): multi-table save/load round-trip + access forms."""
import os
import stat
import tempfile

from _harness import run, eq, ok, raises
from pipeline5.truth.database import Database
from pipeline5.truth.table import Table


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


def _files(directory):
    files = {}
    for name in sorted(os.listdir(directory)):
        with open(os.path.join(directory, name), "rb") as handle:
            files[name] = handle.read()
    return files


def test_a_refused_save_leaves_every_file_as_it_was():
    """A save is all or nothing, as far as a save can be (C-024 refute round 22 and its implications check): it
    wrote table by table - a value that could not be written emptied its table's CSV (the file opened, then the
    write failed), and a file another program held open (Excel) stopped it with the tables before it already
    this run's: a Database half new, half old. Every table is rendered, then every file opened for writing,
    before any is truncated now: a value that cannot be written (located) or a file that cannot be opened (a
    read-only one here, as a lock) leaves every file as it was, none created."""
    a = Table("a", ["uid", "v"], key_columns=["v"])
    b = Table("b", ["uid", "v"], key_columns=["v"])
    a.add(v="one")
    b.add(v="two")
    with tempfile.TemporaryDirectory() as d:
        Database([a, b]).save(d)
        saved = _files(d)
        a.add(v="three")                                        # a change a successful save would write
        fresh = Table("c", ["uid", "v"])                        # a table with no file yet, saved BEFORE b
        database = Database([a, fresh, b])
        b.rows[0]["v"] = "bad \ud83d"                           # (set after the add: its uid hashes the key)
        try:
            database.save(d)
            ok(False, "a value UTF-8 cannot store must stop the save")
        except ValueError as error:
            ok(str(error).startswith("b.v row 0:"), f"located: {error}")
        eq(_files(d), saved, "a value that cannot be written: every file as it was, none created")
        b.rows[0]["v"] = "two"
        locked = os.path.join(d, "b.csv")
        os.chmod(locked, stat.S_IREAD)                          # a file that cannot be opened for writing
        try:
            raises(PermissionError, lambda: database.save(d))
            eq(_files(d), saved, "a file that cannot be opened: every file as it was - c.csv made and removed")
        finally:
            os.chmod(locked, stat.S_IREAD | stat.S_IWRITE)
        database.save(d)
        eq(sorted(_files(d)), ["a.csv", "b.csv", "c.csv"], "then it saves, whole")
        eq(len(Database([Table("a", ["uid", "v"])]).load(d)["a"]), 2, "…this run's rows")


if __name__ == "__main__":
    import sys
    sys.exit(run("database", [
        ("save_load_round_trip_with_foreign_key", test_save_load_round_trip_with_foreign_key),
        ("load_missing_table_is_noop", test_load_missing_table_is_noop),
        ("access_forms", test_access_forms),
        ("duplicate_table_name_rejected", test_duplicate_table_name_rejected),
        ("a_refused_save_leaves_every_file_as_it_was", test_a_refused_save_leaves_every_file_as_it_was),
    ]))
