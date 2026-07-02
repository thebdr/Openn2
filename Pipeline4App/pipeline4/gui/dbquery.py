"""The Database Explorer engine (GUI M3) - load the SSOT tables into an in-memory SQLite DB and run SQL.

PL4's SSOT is RELATIONAL: 14 CSV-with-JSON-cells tables linked by `uid` (and `source_signal`/`db_name`/...).
Loading them into `:memory:` SQLite turns the whole store into a real query surface - cross-table JOINs +
GROUP BY + SQLite's built-in `json_extract()` over the JSON cells - a capability PL3's flat per-phase files
could never offer. Pure (Tk-free) + read-only: it's an in-memory COPY, so any query (even a DELETE) only
touches the throwaway copy; the on-disk CSVs are never modified, and `Refresh` rebuilds it.

Each Database CSV (comma, header, JSON cells stored as their JSON string per `core.table`) becomes one SQLite
table of TEXT columns; JSON columns are queryable as-is via `json_extract(col, '$.path')`.
"""
from __future__ import annotations

import csv
import glob
import os
import sqlite3


def dir_stamp(db_dir: str) -> tuple:
    """A cheap identity of the Database folder: sorted `(filename, mtime_ns, size)` per `*.csv`. Two equal
    stamps -> the loaded in-memory copy is still current, so the explorer skips the rebuild (visiting the
    tab stays free; a phase run that rewrote a table changes the stamp and triggers a reload)."""
    entries = []
    for path in sorted(glob.glob(os.path.join(db_dir, "*.csv"))):
        try:
            meta = os.stat(path)
            entries.append((os.path.basename(path), meta.st_mtime_ns, meta.st_size))
        except OSError:                                  # racing a writer - count it as "changed"
            entries.append((os.path.basename(path), -1, -1))
    return tuple(entries)


def build_memory_db(db_dir: str) -> tuple:
    """Load every `*.csv` under `db_dir` into a fresh in-memory SQLite connection. Returns
    `(connection, {table_name: [columns]})`. Ragged rows are padded/truncated to the header (lenient - a
    hand-edited CSV shouldn't crash the browser).

    `check_same_thread=False`: the explorer BUILDS on a worker thread and QUERIES on the Tk thread -
    never concurrently (the connection is handed over once built), so cross-thread use is safe."""
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    schema: dict = {}
    for path in sorted(glob.glob(os.path.join(db_dir, "*.csv"))):
        name = os.path.splitext(os.path.basename(path))[0]
        with open(path, newline="", encoding="utf-8-sig") as handle:
            reader = csv.reader(handle)
            header = next(reader, [])
            if not header or len(set(header)) != len(header):
                continue                                 # empty or dup-header table - skip (the explorer is lenient)
            width = len(header)
            conn.execute(f'CREATE TABLE "{name}" ({", ".join(chr(34) + c + chr(34) + " TEXT" for c in header)})')
            placeholders = ",".join("?" * width)
            rows = [(r + [""] * width)[:width] for r in reader]
            conn.executemany(f'INSERT INTO "{name}" VALUES ({placeholders})', rows)
            schema[name] = list(header)
    conn.commit()
    return conn, schema


def run_query(conn: sqlite3.Connection, sql: str) -> tuple:
    """Execute `sql` -> `(columns, rows)`. Raises `sqlite3.Error` on a bad query (the caller shows it)."""
    cursor = conn.execute(sql)
    columns = [d[0] for d in cursor.description] if cursor.description else []
    return columns, cursor.fetchall()


# Discoverability: ready-made queries showing SELECT *, json_extract, GROUP BY, and cross-table JOINs.
SAMPLE_QUERIES = (
    ("All signals (200)", "SELECT * FROM signals LIMIT 200"),
    ("Signals by type", "SELECT json_extract(type, '$.type_id') AS type_id, COUNT(*) AS n\n"
                        "FROM signals GROUP BY type_id ORDER BY n DESC"),
    ("Signals in no data block", "SELECT source_cell, combined_FLD, script_type\n"
                                 "FROM signals WHERE datablocks = '[]'"),
    ("Data-block member counts", "SELECT db_name, COUNT(*) AS members\n"
                                 "FROM db_members GROUP BY db_name ORDER BY members DESC"),
    ("Findings by phase + severity", "SELECT phase, severity, COUNT(*) AS n\n"
                                     "FROM validation_issues GROUP BY phase, severity ORDER BY phase"),
    ("Coverage ORPHANs", "SELECT source_cell, script_type, FLD, address FROM coverage WHERE flag = 'ORPHAN'"),
    ("Interface elements with their signal",
     "SELECT ie.interface, ie.signal_name, s.combined_FLD\n"
     "FROM interface_elements ie JOIN signals s ON ie.source_signal = s.uid LIMIT 200"),
    ("Hardware stations + module count",
     "SELECT hs.station_name, COUNT(hm.uid) AS modules\n"
     "FROM hardware_stations hs LEFT JOIN hardware_modules hm ON hm.station_name = hs.station_name\n"
     "GROUP BY hs.station_name ORDER BY modules DESC"),
)
