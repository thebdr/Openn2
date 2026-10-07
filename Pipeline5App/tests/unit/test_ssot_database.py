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


def test_a_hidden_system_or_locked_file_saves_whole_or_not_at_all():
    """C-024 refute round 24: the save's check opened each file to APPEND ("ab") - which Windows grants on a HIDDEN
    or SYSTEM file - then re-created it to write ("wb"), which Windows refuses on such a file: the tables before it
    were already this run's (a Database half new, half old - the audit saying a rule ran ok whose finding was
    recorded). And another program's byte-range lock passed the check too: the save then truncated that file to 0
    bytes. Every file is written IN PLACE now (a hidden / system one keeps its attribute), and locked whole before
    any is written - a lock anywhere in a file refuses the save with every file as it was."""
    if os.name != "nt":
        return                                                   # (Windows attributes and locks)
    import ctypes
    import msvcrt
    attributes = ctypes.windll.kernel32.GetFileAttributesW
    set_attributes = ctypes.windll.kernel32.SetFileAttributesW
    hidden, system, normal = 0x2, 0x4, 0x80
    a = Table("a", ["uid", "v"], key_columns=["v"])
    b = Table("b", ["uid", "v"], key_columns=["v"])
    with tempfile.TemporaryDirectory() as d:
        for flag in (hidden, system):
            a.rows, b.rows = [], []
            a.add(v="one")
            b.add(v="a long first value")
            Database([a, b]).save(d)
            path = os.path.join(d, "b.csv")
            set_attributes(path, flag)
            try:
                a.add(v="three")
                b.rows = []
                b.add(v="two")                                   # SHORTER than before: cut to its new length
                Database([a, b]).save(d)
                eq(_files(d), {"a.csv": a.csv_bytes(), "b.csv": b.csv_bytes()}, f"0x{flag:x}: saved whole, byte for byte")
                eq(attributes(path) & flag, flag, f"0x{flag:x}: …in place - the attribute kept")
            finally:
                set_attributes(path, normal)
        saved = _files(d)
        a.add(v="four")                                          # a change a successful save would write
        fresh = Table("c", ["uid", "v"])                         # a table with no file yet, saved BEFORE b
        holder = open(os.path.join(d, "b.csv"), "r+b")           # another program locks bytes 5..9 of b.csv
        holder.seek(5)
        msvcrt.locking(holder.fileno(), msvcrt.LK_NBLCK, 5)
        try:
            raises(PermissionError, lambda: Database([a, fresh, b]).save(d))
        finally:
            holder.seek(5)
            msvcrt.locking(holder.fileno(), msvcrt.LK_UNLCK, 5)
            holder.close()
        eq(_files(d), saved, "a lock anywhere in a file: every file as it was - none truncated, c.csv made and removed")
        Database([a, fresh, b]).save(d)
        eq(_files(d), {"a.csv": a.csv_bytes(), "b.csv": b.csv_bytes(), "c.csv": fresh.csv_bytes()},
           "the lock gone: saved whole")


if __name__ == "__main__":
    import sys
    sys.exit(run("database", [
        ("save_load_round_trip_with_foreign_key", test_save_load_round_trip_with_foreign_key),
        ("load_missing_table_is_noop", test_load_missing_table_is_noop),
        ("access_forms", test_access_forms),
        ("duplicate_table_name_rejected", test_duplicate_table_name_rejected),
        ("a_refused_save_leaves_every_file_as_it_was", test_a_refused_save_leaves_every_file_as_it_was),
        ("a_hidden_system_or_locked_file_saves_whole_or_not_at_all",
         test_a_hidden_system_or_locked_file_saves_whole_or_not_at_all),
    ]))
