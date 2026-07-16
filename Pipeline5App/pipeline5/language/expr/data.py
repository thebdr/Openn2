"""Data functions - the host-table layer of the expression engine (M-E1 minimal; evolves in M-E3).

The host passes its DB tables under a RESERVED ctx key `_db` = a dict {table_name: list[row-dict]}. The
data funcs read those tables:

    where(table, pred)            -> the list of rows for which `pred` is truthy (pred evaluated per row,
                                     the ROW is the scope - $col refers to that row's cell)
    first(table, pred)            -> the first such row, or {} (an empty dict) when none
    lookup(table, key_col, key_val, val_col)  -> `val_col` of the first row whose `key_col` == key_val, "" if none
    unique(col, table)            -> the list of DISTINCT non-empty values of `col` (first-seen order)
    count(table[, pred])          -> number of rows (optionally only those passing `pred`)
    node_of($bit, table)          -> the row of `table` that "owns" the address `$bit` by positional
                                     range-containment: the node whose [start_byte, end_byte] (numeric)
                                     contains the numeric byte of `$bit`; {} when none.

DESIGN NOTES / flagged simplest-coherent choices (this layer is deliberately minimal, M-E3 will revisit):
  * `where`/`first`/`count`'s `pred` is an EXPRESSION compiled against a per-row scope (every column is a
    valid $name -> the pred runs with scope=None so any $col resolves to that row's cell or "").
  * `lookup`/`node_of` take the table as a NAME string (a literal) - the engine resolves it from `_db`.
    For symmetry `where`/`first`/`count`/`unique` also take the table as a bare table-NAME word (parsed
    as a special table token), NOT a $field - tables are structural, not data cells. FLAG: this couples
    the surface to a table-name word; M-E3 may admit a $-bound table handle.
  * `node_of` reads the node row's byte range from columns `start_byte`/`end_byte` and the queried bit's
    byte from the leading digits after the I/Q letter (e.g. "I12.3" -> 12). FLAG: column names are fixed
    here; M-E3 can make them configurable.
"""
from __future__ import annotations

import re

from .runtime import s, truthy

# byte = the integer between the leading I/Q (optional) and the optional ".bit"
_BYTE_RE = re.compile(r"[A-Za-z%]*\s*(\d+)")

_DB_KEY = "_db"


def _table(ctx, name):
    db = ctx.get(_DB_KEY) or {}
    return db.get(name, []) or []


def _byte_of(addr) -> float | None:
    m = _BYTE_RE.match(s(addr).strip())
    if not m:
        return None
    return float(m.group(1))


def where(ctx, table_name, pred_fn) -> list:
    """All rows of `table_name` for which `pred_fn(row)` is truthy. `pred_fn` is a compiled predicate
    taking a per-row ctx (the row's own cells as $fields)."""
    rows = _table(ctx, table_name)
    if pred_fn is None:
        return list(rows)
    out = []
    for r in rows:
        if truthy(pred_fn(dict(r))):
            out.append(r)
    return out


def first(ctx, table_name, pred_fn) -> dict:
    """The first matching row, or {} when none."""
    rows = where(ctx, table_name, pred_fn)
    return rows[0] if rows else {}


def lookup(ctx, table_name, key_col, key_val, val_col) -> str:
    """`val_col` of the first row whose `key_col` equals `key_val` (string compare); "" when none."""
    target = s(key_val)
    for r in _table(ctx, table_name):
        if s(r.get(key_col, "")) == target:
            return s(r.get(val_col, ""))
    return ""


def unique(ctx, col, table_name) -> list:
    """The DISTINCT non-empty values of `col` across `table_name`, in first-seen order."""
    seen, out = set(), []
    for r in _table(ctx, table_name):
        v = s(r.get(col, "")).strip()
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def count(ctx, table_name, pred_fn) -> float:
    """Number of rows in `table_name` (optionally only those passing `pred_fn`)."""
    if pred_fn is None:
        return float(len(_table(ctx, table_name)))
    return float(len(where(ctx, table_name, pred_fn)))


def node_of(ctx, bit, table_name) -> dict:
    """The row of `table_name` whose [start_byte, end_byte] numeric range contains `bit`'s byte; {} else."""
    target = _byte_of(bit)
    if target is None:
        return {}
    for r in _table(ctx, table_name):
        try:
            lo = float(s(r.get("start_byte", "")))
            hi = float(s(r.get("end_byte", "")))
        except ValueError:
            continue
        if lo <= target <= hi:
            return r
    return {}
