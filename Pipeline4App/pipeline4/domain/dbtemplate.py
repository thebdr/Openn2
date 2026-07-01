"""Two small grammars for the config-driven data-block subsystem (phase 520), both validate-and-halt.
Clean-room port of PL3's `dbtemplate` - pure + data-independent, no PL4-specific coupling:

1. `render(template, ctx)` - a PEP-3101 format string (`{name}` / `{name:spec}`) over a context dict,
   restricted to bare field names (no attribute/index access, no positional args); a numeric format spec
   coerces the (string) value first, so `{cabinet:03d}` works on the cell `'1'` -> `'001'`.
2. `compile_for_each(expr)` -> `ForEach` - the iteration DSL:
       (blank)                                     -> a single literal item
       row [where <pred>]                          -> one per signals-table row (optionally filtered)
       <var> in unique(<column>) [where <pred>]    -> one per DISTINCT value of <column>, bound to <var>
   `<pred>` is a boolean over a row: `numeric(col)`, `col = "x"`, `col != "x"`, `col in ["a","b"]`,
   `col ~ /regex/`, `not P`, `P and Q`, `P or Q`, `( P )`.

Both raise `DbTemplateError` on a bad template / expression / unknown field; the 520 caller logs it and
HALTS the pipeline before the OP4 import ever sees a malformed name.
"""
from __future__ import annotations

import re
import string

from pipeline4.core import expr
from pipeline4.core.expr.parser import referenced_fields


class DbTemplateError(ValueError):
    """A malformed template or for_each expression (-> logged + pipeline halt)."""


# --- 1. PEP-3101 value/name templates ------------------------------------------------------------ #
# A hole body is a native `{$field}` reference (dotted `$obj.key` allowed) - NOT a forgotten-`$` bare name,
# `{0}` positional, or `{a[i]}` access. The engine (expr.render) does the real validation; this front-end
# guard gives a clear error when an author writes `{name}` instead of `{$name}`.
_FIELD_RE = re.compile(r"\$[A-Za-z_][\w.]*\Z")
# A {hole} body up to the optional ':spec' (mirrors PEP-3101 parsing).
_HOLE_FIELD = re.compile(r"\{([^{}:]*)(?::[^{}]*)?\}")


def render(template, ctx: dict) -> str:
    """Render a native `{$field}` template against `ctx`; raise DbTemplateError on an unknown field / bad
    spec. DELEGATES to the unified `expr.render` (mode="strict": a missing field raises); `expr.ExprError`
    is re-raised as `DbTemplateError` so the 520 halt path is unchanged. The up-front guard requires each
    hole to be a `{$name}` DB reference (rejecting a forgotten-`$` bare name, `{0}`, `{a[i]}` access)."""
    s = str(template if template is not None else "")
    for field in _HOLE_FIELD.findall(s):
        if field and not _FIELD_RE.match(field):
            raise DbTemplateError(f"invalid template field {{{field}}} (use a {{$name}} DB reference)")
    try:
        return expr.render(s, ctx, mode="strict")
    except expr.ExprError as e:
        raise DbTemplateError(f"bad template {template!r}: {e}")


def template_fields(template) -> set:
    """The bare field names a template references (for up-front validation)."""
    out = set()
    for _lit, field, _spec, _conv in string.Formatter().parse(str(template or "")):
        if field:
            out.add(field)
    return out


# --- 2. the for_each iteration DSL --------------------------------------------------------------- #
# The HEAD is host-parsed (a row-generating loop); the optional `where <pred>` is a core/expr predicate
# (DB-refs `$col`, evaluated per candidate row by `expr.test`). The loop stays a code pass; only the
# boolean predicate moved onto the unified engine.
_HEAD_ROW = re.compile(r"row\Z", re.IGNORECASE)
_HEAD_UNIQUE = re.compile(r"(\w+)\s+in\s+unique\(\s*\$?(\w+)\s*\)\Z", re.IGNORECASE)
_WHERE = re.compile(r"\bwhere\b", re.IGNORECASE)


def _cell(row, col) -> str:
    return str(row.get(col, "") if row else "").strip()


class ForEach:
    """A compiled iteration expression. `evaluate(rows)` yields `(binding, rep_row)`:
      - literal: one `({}, None)`;
      - row:     one `({}, row)` per row passing the predicate;
      - unique:  one `({var: value}, first_row)` per DISTINCT value of `column` (rows pre-filtered by the
                 predicate; a `|`-multi-valued cell is split), in first-seen order.
    `columns` is every `$col` the predicate (+ the `unique` column) names - the engine checks them against
    the real row keys for the matches-nothing WARN. `predicate` is a core/expr string (None = no filter)."""

    def __init__(self, kind, var, column, predicate, columns, source):
        self.kind, self.var, self.column = kind, var, column
        self._pred, self.columns, self.source = predicate, columns, source

    def evaluate(self, rows):
        rows = rows or []
        if self.kind == "literal":
            yield {}, None
            return
        keep = (r for r in rows if expr.test(self._pred, r)) if self._pred else iter(rows)
        if self.kind == "row":
            for r in keep:
                yield {}, r
            return
        seen = set()                                          # kind == "unique"
        for r in keep:
            cell = _cell(r, self.column)
            for v in (cell.split("|") if "|" in cell else [cell]):
                v = v.strip()
                if v and v not in seen:
                    seen.add(v)
                    yield {self.var: v}, r

    def __repr__(self):
        return f"ForEach({self.source!r})"


def compile_for_each(expr_text) -> ForEach:
    """Compile a for_each expression. The HEAD (`row` / `<var> in unique($col)`) is host-parsed (a
    row-generating loop); the optional `where <pred>` is a core/expr predicate (DB-refs `$col`), validated
    NOW (a syntax error -> DbTemplateError, so the 520 caller's halt path is unchanged) and evaluated per
    row at generate. Raise DbTemplateError on a bad head or predicate."""
    s = str(expr_text or "").strip()
    if not s:
        return ForEach("literal", None, None, None, set(), "")
    head, pred = s, None
    m = _WHERE.search(s)
    if m:
        head, pred = s[:m.start()].strip(), s[m.end():].strip()
    cols = set()
    if pred:
        try:
            expr.compile_expr(pred, None)                       # validate the predicate syntax now
        except (expr.ExprError, re.error) as e:                 # re.error: a bad /regex/ compiled by `~`
            raise DbTemplateError(f"for_each: bad predicate {pred!r}: {e}")
        cols = {c.lstrip("$") for c in referenced_fields(pred)}  # the $cols it names (matches-nothing WARN)
    if _HEAD_ROW.fullmatch(head):
        return ForEach("row", None, None, pred, cols, s)
    hm = _HEAD_UNIQUE.fullmatch(head)
    if hm:
        col = hm.group(2)
        return ForEach("unique", hm.group(1), col, pred, cols | {col}, s)
    raise DbTemplateError(f"for_each: expected 'row' or '<var> in unique($col)', got {head!r}")
