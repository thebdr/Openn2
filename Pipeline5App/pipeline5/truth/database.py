"""The PL4 single source of truth: an in-memory `Database` of named `Table`s, persisted to one folder.

The Database holds every entity table (the schema set is declared in code - see DESIGN section 2). Phases
READ it (queries over the tables) and WRITE their created entities back into it, so one place holds
everything the pipeline retrieved, inferred, or created.

`save(directory)` writes one CSV-with-JSON-cells per table into the top-level Database/ folder
(`Shared/Database/` or `<project>/Database/`, DESIGN section 10.3). `load(directory)` reads them back into
the SAME declared schemas, fully typed - so a run can resume from a saved Database with no re-derivation.
"""
from __future__ import annotations

import contextlib
import os

from pipeline5.truth.table import Table


class Database:
    """A named collection of `Table`s. Construct it with the declared (empty) table schemas; fill the
    tables as phases run; `save`/`load` round-trip the whole thing to a folder."""

    def __init__(self, tables):
        self._tables: dict = {}
        for table in tables:
            if table.name in self._tables:
                raise ValueError(f"duplicate table name {table.name!r}")
            self._tables[table.name] = table

    # --- access ---------------------------------------------------------------------------------- #
    def table(self, name) -> Table:
        return self._tables[name]

    def add_table(self, table) -> Table:
        """Register a table a phase built (e.g. 520's `db_members` / `instance_dbs`) so `save` writes it
        and later phases read it. Raises on a duplicate name (use `table(name).rows = ...` to refill)."""
        if table.name in self._tables:
            raise ValueError(f"duplicate table name {table.name!r}")
        self._tables[table.name] = table
        return table

    def __getitem__(self, name) -> Table:
        return self._tables[name]

    def __contains__(self, name) -> bool:
        return name in self._tables

    def names(self) -> list:
        return list(self._tables)

    # --- persistence ----------------------------------------------------------------------------- #
    def save(self, directory) -> None:
        """Write every table to `<directory>/<table>.csv` (creating the directory) - all or nothing, as far as a
        save can be: EVERY table rendered first (`Table.csv_bytes` - a value that cannot be written raises,
        located), then EVERY file opened for writing without truncating it (a file another program holds
        open - Excel's deny-write lock - or a read-only one raises there; a file this save created is removed
        again), and only then written. A refused save leaves every file as it was: never a truncated table,
        never a Database half this run's and half the last (C-024 refute round 22 + its implications check).
        Only a failure DURING the writes - a full disk, a lock taken in between - can stop it part-way."""
        payloads = [(os.path.join(directory, f"{table.name}.csv"), table.csv_bytes())
                    for table in self._tables.values()]
        os.makedirs(directory, exist_ok=True)
        created = []
        try:
            for path, _data in payloads:                    # every file writable BEFORE any is truncated
                existed = os.path.exists(path)
                with open(path, "ab"):
                    pass
                if not existed:
                    created.append(path)
        except OSError:
            for path in created:
                with contextlib.suppress(OSError):
                    os.remove(path)
            raise
        for path, data in payloads:
            with open(path, "wb") as handle:
                handle.write(data)

    def load(self, directory) -> "Database":
        """Read each declared table from `<directory>/<table>.csv` if present; an absent file leaves
        that table empty (no error) - so a partial Database loads cleanly. Returns self."""
        for table in self._tables.values():
            path = os.path.join(directory, f"{table.name}.csv")
            if os.path.exists(path):
                table.read_csv(path)
        return self
