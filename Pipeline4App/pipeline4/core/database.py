"""The PL4 single source of truth: an in-memory `Database` of named `Table`s, persisted to one folder.

The Database holds every entity table (the schema set is declared in code - see DESIGN section 2). Phases
READ it (queries over the tables) and WRITE their created entities back into it, so one place holds
everything the pipeline retrieved, inferred, or created.

`save(directory)` writes one CSV-with-JSON-cells per table into the top-level Database/ folder
(`Shared/Database/` or `<project>/Database/`, DESIGN section 10.3). `load(directory)` reads them back into
the SAME declared schemas, fully typed - so a run can resume from a saved Database with no re-derivation.
"""
from __future__ import annotations

import os

from pipeline4.core.table import Table


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

    def __getitem__(self, name) -> Table:
        return self._tables[name]

    def __contains__(self, name) -> bool:
        return name in self._tables

    def names(self) -> list:
        return list(self._tables)

    # --- persistence ----------------------------------------------------------------------------- #
    def save(self, directory) -> None:
        """Write every table to `<directory>/<table>.csv` (creating the directory)."""
        os.makedirs(directory, exist_ok=True)
        for table in self._tables.values():
            table.write_csv(os.path.join(directory, f"{table.name}.csv"))

    def load(self, directory) -> "Database":
        """Read each declared table from `<directory>/<table>.csv` if present; an absent file leaves
        that table empty (no error) - so a partial Database loads cleanly. Returns self."""
        for table in self._tables.values():
            path = os.path.join(directory, f"{table.name}.csv")
            if os.path.exists(path):
                table.read_csv(path)
        return self
