"""The single data source for block builders: the staged `signals` table rows.

A thin, read-only accessor so a hand-written builder (`builders.py`) can pull exactly the rows it wants.
There are NO rules here. Clean-room port of PL3's `domain/blocks/database.py`, adapted for PL4: the
`datablocks` and `matrix_areas` cells are real JSON **list** cells here (not PL3's `|`-joined strings), so
`by_db`/`by_area`/`areas` read the lists directly - no split-on-`|`.
"""
from __future__ import annotations


def _as_list(value) -> list:
    """A PL4 list cell -> a list of trimmed strings; tolerate a legacy `|`-string or a scalar."""
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    return [v.strip() for v in str(value or "").split("|") if v.strip()]


class Database:
    def __init__(self, rows):
        self.rows = list(rows or [])

    def __iter__(self):
        return iter(self.rows)

    def __len__(self):
        return len(self.rows)

    # --- convenience filters (a builder may also just iterate `db` and branch itself) --- #
    def where(self, pred) -> list:
        """Rows for which pred(row) is truthy."""
        return [r for r in self.rows if pred(r)]

    def first(self, pred):
        return next((r for r in self.rows if pred(r)), None)

    def by_type(self, *script_types) -> list:
        """Rows whose script_type is one of `script_types` (case-insensitive)."""
        want = {str(t).strip().upper() for t in script_types}
        return [r for r in self.rows if str(r.get("script_type", "")).strip().upper() in want]

    def by_db(self, db_name: str) -> list:
        """Rows that are a member of the data block `db_name` (the staged `datablocks` list cell)."""
        return [r for r in self.rows if db_name in _as_list(r.get("datablocks"))]

    def by_tagtable(self, tagtable: str) -> list:
        return [r for r in self.rows if str(r.get("tagtable", "")).strip() == tagtable]

    def by_area(self, area: str) -> list:
        """Rows that belong to the C&E area `area` (the staged `matrix_areas` list cell)."""
        return [r for r in self.rows if area in _as_list(r.get("matrix_areas"))]

    def areas(self) -> list:
        """The distinct C&E areas present, in first-seen order."""
        seen = []
        for r in self.rows:
            for a in _as_list(r.get("matrix_areas")):
                if a not in seen:
                    seen.append(a)
        return seen
