"""The single data source for block builders: the staged IODatabase (ctx.rows).

A thin, read-only accessor so a hand-written builder (domain/blocks/builders.py) can pull exactly
the rows it wants. There are NO rules here - a builder queries `db` however it likes and shapes a
Table. Every row is a staged dict (the IoList canonical columns + the enrichment/identity columns:
name_in_db, name_in_tagtable, tagtable, datablocks, matrix_areas, areas_description, diag_*, etc.).
"""
from __future__ import annotations


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
        """Rows whose Script Type (AB) is one of `script_types` (case-insensitive)."""
        want = {str(t).strip().upper() for t in script_types}
        return [r for r in self.rows if str(r.get("script_type", "")).strip().upper() in want]

    def by_db(self, db_name: str) -> list:
        """Rows that are a member of the data block `db_name` (the staged `datablocks` column)."""
        return [r for r in self.rows
                if db_name in [d.strip() for d in str(r.get("datablocks", "")).split("|") if d.strip()]]

    def by_tagtable(self, tagtable: str) -> list:
        return [r for r in self.rows if str(r.get("tagtable", "")).strip() == tagtable]

    def by_area(self, area: str) -> list:
        """Rows that belong to the C&E area `area` (the staged `matrix_areas` column)."""
        return [r for r in self.rows
                if area in [a.strip() for a in str(r.get("matrix_areas", "")).split("|") if a.strip()]]

    def areas(self) -> list:
        """The distinct C&E areas present, in first-seen order."""
        seen = []
        for r in self.rows:
            for a in str(r.get("matrix_areas", "")).split("|"):
                a = a.strip()
                if a and a not in seen:
                    seen.append(a)
        return seen
