"""A typed table persisted as a CSV with JSON cells - the PL4 storage primitive.

A `Table` is one entity table (signals, db_members, diagnosis_entries, ...). It declares its column
ORDER and which columns hold STRUCTURED values (lists/objects) - the `json_columns`. On write those
columns are JSON-encoded into the cell; every other column is plain text. On read the same columns are
JSON-decoded back into real Python lists/dicts. That is what lets a single cell hold
`["07_DOOR", "00_Commissioning"]` or a whole resolved-type object WITHOUT the '|'-join + split-on-read
workarounds Pipeline3 needed (and the "leftmost db name" hack, and re-attaching the type dict).

The container is still a comma CSV (one file per table) so it stays git-diffable, Excel-openable, and
renderable in the GUI grid. The schema (columns + json_columns) lives in CODE, not in the file - the
file is pure data. There is NO legacy '|'-format reader: PL4 is a clean skeleton (DESIGN section 10.6).

A row is a plain `dict`. If a table declares `key_columns`, `add()` stamps each row with a content-hash
`uid` (see `core.keys`) computed from those fields, so the row is stable across re-runs and document
revisions and other tables can foreign-key to it.
"""
from __future__ import annotations

import csv
import json

from pipeline5.truth.content_hash import uid as content_uid


def encode_cell(value) -> str:
    """A structured value -> the text stored in a JSON cell. Compact and DETERMINISTIC (dict keys
    sorted) so a table round-trips byte-stably and diffs cleanly; list order is preserved (meaningful).
    `None` -> '' (an empty cell), distinct from an empty list `[]` which encodes as '[]'. JSON-cell
    objects must use STRING keys (the JSON object model). `allow_nan=False` rejects NaN/Infinity at write
    time rather than emit non-standard JSON tokens that strict readers reject."""
    if value is None:
        return ""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def decode_cell(text: str):
    """The inverse of `encode_cell`: '' -> `None`; otherwise parse the JSON back to a list/dict/scalar."""
    if text == "":
        return None
    return json.loads(text)


def _scalar_text(value) -> str:
    """A non-JSON (plain) cell: `None` -> '', everything else stringified. (CSV cells are text; a plain
    column reads back as a string - the caller coerces if it needs an int. JSON columns keep their type.)"""
    return "" if value is None else str(value)


class Table:
    """One entity table: an ordered column schema, the set of JSON-valued columns, and the rows."""

    def __init__(self, name, columns, json_columns=(), key_columns=()):
        self.name = name
        self.columns = list(columns)
        self.json_columns = set(json_columns)
        self.key_columns = list(key_columns)      # the identifying fields -> this row's uid
        self.rows: list[dict] = []

    # --- building -------------------------------------------------------------------------------- #
    def add(self, **values) -> dict:
        """Append a row from keyword values and return it. If `key_columns` are declared and no `uid`
        was supplied, stamp a content-hash `uid` from the key fields. Keys outside `columns` are kept
        (the schema is the column ORDER for I/O, not a wall)."""
        return self.add_row(values)

    def add_row(self, row: dict) -> dict:
        row = dict(row)
        if self.key_columns and not row.get("uid"):
            row["uid"] = content_uid(*(row.get(key) for key in self.key_columns))
        self.rows.append(row)
        return row

    def extend(self, rows) -> "Table":
        """Append many rows (each through `add_row`, so uid-stamping applies uniformly)."""
        for row in rows:
            self.add_row(row)
        return self

    def __iter__(self):
        return iter(self.rows)

    def __len__(self) -> int:
        return len(self.rows)

    # --- query ----------------------------------------------------------------------------------- #
    def where(self, predicate) -> list:
        """Every row satisfying `predicate(row)`. The one query primitive; entity-specific helpers
        (by_type / by_db / by_area / ...) are built on top of it where each table is defined."""
        return [row for row in self.rows if predicate(row)]

    def first(self, predicate):
        """The first row satisfying `predicate(row)`, else `None`."""
        for row in self.rows:
            if predicate(row):
                return row
        return None

    def by_uid(self, uid_value):
        """The row whose `uid` == `uid_value` (the foreign-key lookup), else `None`."""
        return self.first(lambda row: row.get("uid") == uid_value)

    def duplicate_uids(self) -> set:
        """The set of `uid`s appearing on more than one row - a build-time guard against two entities
        hashing equal (which would corrupt identity + any foreign key pointing at that uid). Empty = clean."""
        seen, duplicates = set(), set()
        for row in self.rows:
            value = row.get("uid")
            if value:
                if value in seen:
                    duplicates.add(value)
                seen.add(value)
        return duplicates

    # --- persistence ----------------------------------------------------------------------------- #
    def effective_columns(self) -> list:
        """The declared `columns` first, then any extra keys present in the rows - **sorted**, so the
        header (hence the bytes) is DETERMINISTIC regardless of row/dict insertion order. A non-deterministic
        header would break the byte-stable parity-diff the whole pipeline relies on."""
        declared = list(self.columns)
        known = set(declared)
        extras = sorted({key for row in self.rows for key in row if key not in known})
        return declared + extras

    def write_csv(self, path) -> None:
        """Write the table as a comma CSV; `json_columns` are JSON-encoded, the rest plain text. A
        structured value (list/dict) in a column NOT declared `json_columns` is a bug - it would `str()`
        to a lossy Python repr - so raise instead of silently corrupting it."""
        columns = self.effective_columns()
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(columns)
            for row in self.rows:
                cells = []
                for column in columns:
                    value = row.get(column)
                    if column in self.json_columns:
                        cells.append(encode_cell(value))
                    elif isinstance(value, (list, dict)):
                        raise ValueError(f"{self.name}.{column}: holds a {type(value).__name__} but is not "
                                         f"declared in json_columns (it would be stored lossily as a repr)")
                    else:
                        cells.append(_scalar_text(value))
                writer.writerow(cells)

    def read_csv(self, path) -> "Table":
        """Load rows from a comma CSV into this table's schema; the declared `json_columns` are
        JSON-decoded back to lists/dicts, every other column stays a string. Replaces `self.rows`. These
        files are human/Excel-editable, so it VALIDATES: a duplicate header, a ragged row, or a malformed
        JSON cell raises a LOCATED error (table/column/row) instead of silently dropping or mis-reading data."""
        with open(path, newline="", encoding="utf-8-sig") as handle:
            reader = csv.reader(handle)
            header = next(reader, [])
            if len(set(header)) != len(header):
                raise ValueError(f"{self.name}: duplicate column names in header {header}")
            self.rows = []
            for index, raw in enumerate(reader):
                if len(raw) != len(header):
                    raise ValueError(f"{self.name}: row {index} has {len(raw)} cells, header has {len(header)}")
                row = {}
                for column, text in zip(header, raw):
                    if column in self.json_columns:
                        try:
                            row[column] = decode_cell(text)
                        except json.JSONDecodeError as error:
                            raise ValueError(f"{self.name}.{column} row {index}: not valid JSON: {text!r}") from error
                    else:
                        row[column] = text
                self.rows.append(row)
        return self
