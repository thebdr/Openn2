"""The Table a block builder returns - the clean, single thing the whole phase is about (verbatim port
of PL3's `domain/blocks/table.py`).

A Table is just `columns` (ordered headers) + `rows` (list of dicts keyed by column). A builder fills it
from the Database however it likes; the engine serializes it into the `$/#/%/@` CreationInfo CSV.

Conventions the engine understands when serializing (all optional - a template can be anything):
- a column named `TemplateType` is emitted as the first `%`/`@` column, unwrapped (default "01").
- a column whose name starts with `#` is emitted unwrapped (a meta column), in place.
- every other column is a template placeholder: emitted wrapped as `!!<column>$$`.
- a cell whose value is a list is the horizontal ITERATOR: written across consecutive cells; such a
  column is emitted last. (Pad it yourself in Python if a template needs a fixed width.)
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Table:
    name: str                                  # the block/output name (template stem, prefix dropped)
    columns: list = field(default_factory=list)
    rows: list = field(default_factory=list)   # list[dict]

    def add(self, template_type: str = "01", **values) -> "Table":
        """Append one row. `template_type` -> the TemplateType column; **values are the placeholder
        (or `#meta`) columns. New columns are tracked in first-seen order."""
        row = {"TemplateType": str(template_type), **values}
        for k in row:
            if k not in self.columns:
                self.columns.append(k)
        self.rows.append(row)
        return self

    def add_row(self, row: dict) -> "Table":
        """Append a pre-built row dict (use when you want full control over the columns)."""
        for k in row:
            if k not in self.columns:
                self.columns.append(k)
        self.rows.append(dict(row))
        return self

    def __len__(self):
        return len(self.rows)
