"""TEMPEMPLATOR - the recursive text-template renderer behind the chain-reaction `file` action.

The name honors its origin: the user's Excel/VBA Tempemplator tool (GenerationManager.bas), whose
per-object parameter rows expanded named templates recursively into generated SCL - one REGION per
belt with fully wired FB calls. This module is that engine rebuilt on `language/expr` (the app's one
expression language), with the constructs mapped 1:1 and upgraded:

    Tempemplator (VBA)                  here
    ------------------------------      ------------------------------------------------------
    $Param$ substitution                {$field} expr render holes (strict - a typo'd field is a
                                        located error, never a silent blank)
    «NestedTemplate» call               @use <TemplateName>       (recursive, cycle-guarded)
    «for{$N$:«tpl»} + $IterableIndex$   @for $i in 1..{$N}: @use tpl     (the loop var in scope)
    - (impossible in the original)      @for $row in <table> where <pred>   (the SSOT upgrade:
                                        loop over table rows - `where()` semantics, the row dict
                                        is the loop value, fields via {$row.field})
    «if{c ? a : b} inline               if(c, a, b) inside a {hole} - expr already has it;
                                        block-level branching is @if <pred> / @else / @end
    =out sheet                          the engine's APPEND-to-file action (not this module's job)

The DIVISION OF LABOR mirrors the original's guillemet/dollar split: `@` directives are STRUCTURE
(this module's grammar), `{...}` holes are VALUES (delegated wholesale to expr.render - every expr
function works in a hole). A template is a plain multi-line string; templates live as named entries
in the per-system `chain_reactions/templates.yaml` and reference each other freely.

THE GRAMMAR (line-based; a directive line's own indentation is consumed, body lines emit verbatim):

    @use <name>                          splice the named template here, in the CURRENT scope
    @for $var in <a>..<b>                inclusive integer range; both ends are rendered fragments
                                         (so `1..{$NumPhotocells}` works); $var = the integer
    @for $var in <table> [where <pred>]  one iteration per (matching) row of ctx["_db"][<table>];
                                         $var = the row dict (fields via $var.field); <pred> is an
                                         expr predicate evaluated with the ROW as its scope -
                                         exactly expr's where() semantics (a /regex/ in it is
                                         one literal: its `..` or `:` never splits the line)
    @for ... : <one line>                the inline body form (the line may itself be a directive)
    @if <pred> / @else / @end            block conditional (expr.test); nests freely
    anything else                        a literal line - {expr} holes rendered STRICT

WHAT "STRICT" CATCHES (refuter round 6, resolved against C-002): a missing TOP-LEVEL field, and -
inside a TABLE loop - a `$row.column` naming no column of that table (a SCHEMA check - the columns
are every key its rows carry; the reaction engine hands over rows carrying every DECLARED column:
`{$r.tagg}` over `signals` is a located error; a range var has no columns at all). Deeper sub-keys
of a JSON cell (`$r.type.type_id`) and `{$_params...}` keys stay OPTIONAL per C-002 - blank when
absent, like get_param - so guard or default them (`@if present($r.type.type_id)`, `coalesce(...)`).
Predicates (@if, `where`) are LENIENT by design (the guard idiom): a misspelled name reads blank.

SCOPE (the chain-reaction E1 layering, built by the CALLER - see
src://pipeline5/phases/chain_reactions/engine.py): the matched source row's fields at top level,
`_params` = the project params (dotted access: {$_params.project_code}), `_rule` = {name, hook},
`_db` = {table: rows} for the query loops and expr's data functions. Loop vars stack on top,
shadowing while their loop runs.

Every failure - unknown template, template cycle, unbalanced @if/@for, a bad expression, an
unknown loop table or column, a non-finite range end - raises a LOCATED `TempemplatorError`
(template name + line number); the reaction engine turns it into a finding, never a crash.
"""
from __future__ import annotations

import re

from pipeline5.language import expr
from pipeline5.language.expr import ExprError

_MAX_DEPTH = 32          # @use nesting backstop (the cycle guard catches loops; this catches towers)
# `$var in <iterable>` - ANY whitespace around `in` (a tab too - refuter round 6); the var must be
# a name a {$var} hole can reference (expr's field-name shape)
_FOR_HEAD = re.compile(r"^\$([A-Za-z_]\w*)\s+in\s+(\S.*)$", re.IGNORECASE | re.DOTALL)
_HOLE = re.compile(r"\{([^{}]*)\}")      # the {expr} hole shape expr.render substitutes


class TempemplatorError(Exception):
    """A located template failure: which template, which line (1-based), what went wrong."""

    def __init__(self, template: str, line: int, message: str):
        self.template, self.line, self.message = template, line, message
        super().__init__(f"template {template!r} line {line}: {message}")


def render_template(name: str, templates: dict, ctx: dict) -> str:
    """Render the named template against `ctx` and return the text (lines joined by '\\n', no
    trailing newline - the file action adds it). `templates` is the {name: body} mapping from
    templates.yaml; only STRING entries are text templates (a list entry is a ROW template - the
    add_rows action's shape - and is not renderable here)."""
    return "\n".join(_render_named(name, templates, ctx, stack=(), site=("<call>", 0), schemas={}))


def _template_lines(name: str, templates: dict, stack: tuple, site: tuple) -> list:
    """Resolve a template name to its body lines, guarding unknown names, non-text bodies, cycles,
    and runaway nesting. `site` = (template, line) of the referencing @use, for located errors."""
    where, line = site
    if name not in templates:
        raise TempemplatorError(where, line, f"unknown template {name!r} (not in templates.yaml)")
    body = templates[name]
    if not isinstance(body, str):
        raise TempemplatorError(where, line,
                                f"template {name!r} is a ROW template (a list), not text - "
                                "@use/file rendering needs a text template")
    if name in stack:
        raise TempemplatorError(where, line,
                                f"template cycle: {' -> '.join((*stack, name))}")
    if len(stack) >= _MAX_DEPTH:
        raise TempemplatorError(where, line, f"@use nesting deeper than {_MAX_DEPTH}")
    return body.splitlines()


def _render_named(name: str, templates: dict, ctx: dict, stack: tuple, site: tuple, schemas: dict) -> list:
    lines = _template_lines(name, templates, stack, site)
    out, _next = _render_block(lines, 0, name, templates, ctx, (*stack, name), schemas)
    return out


def _split_top(text: str, marker: str) -> tuple:
    """Split `text` at the FIRST top-level occurrence of `marker` (outside {...} holes, (...)/[...]
    call arguments, quotes and /regex/ literals). Returns (head, tail) or (text, None) when absent - how the @for inline `:` and
    the range `..` are found without tripping over colons/dots inside expressions (a `where $tag ~
    /^P..1$/` predicate is one regex, not a range - refuter round 7; expr has no `/` operator, so an
    unquoted `/` always opens a regex, exactly as render's hole splitter reads it)."""
    depth, parens, i, in_q = 0, 0, 0, ""
    while i < len(text):
        ch = text[i]
        if in_q:
            if ch == "\\":                                  # an escaped char inside a string/regex
                i += 2
                continue
            if ch == in_q:
                in_q = ""
        elif ch in "\"'/":
            in_q = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth = max(0, depth - 1)
        elif ch in "([":                                    # a call's args: a slice `0:1`, a `let(n := ...)`
            parens += 1                                     # (refuter round 8)
        elif ch in ")]":
            parens = max(0, parens - 1)
        elif depth == 0 and parens == 0 and text.startswith(marker, i):
            return text[:i], text[i + len(marker):]
        i += 1
    return text, None


def _check_loop_columns(line: str, template: str, line_no: int, schemas: dict) -> None:
    """The table-loop SCHEMA check: a `$var.column` hole whose `$var` is an active loop variable must
    name a column of that loop's table (a range var has none). Only the FIRST level is a column -
    deeper keys live inside a JSON cell and stay optional (C-002)."""
    for body in _HOLE.findall(line):
        for path in expr.hole_paths(body) or ():            # PARSED: a data-function predicate's row
            head, _dot, rest = path.partition(".")          # column / a let-bound name is not a loop
            if rest and head in schemas:                    # row's column (refuter round 9)
                column = rest.split(".", 1)[0]
                if column not in schemas[head]:
                    known = ", ".join(sorted(schemas[head])) or "none - a range variable is a number"
                    raise TempemplatorError(template, line_no,
                                            f"${head}.{column}: the loop's table has no column "
                                            f"{column!r} (columns: {known})")


def _render_line(line: str, template: str, line_no: int, ctx: dict, schemas: dict) -> str:
    """A literal line: render its {expr} holes STRICT (a missing field / bad expr is an authoring
    error the engine must surface as a finding, never a silent blank)."""
    try:
        if schemas:
            _check_loop_columns(line, template, line_no, schemas)
        return expr.render(line, ctx, mode="strict")
    except TempemplatorError:
        raise                                               # already located (the column check)
    except ExprError as error:
        raise TempemplatorError(template, line_no, str(error)) from error
    except Exception as error:                              # the backstop: still LOCATED, never raw
        raise TempemplatorError(template, line_no, f"{type(error).__name__}: {error}") from error


def _test(pred: str, scope: dict, template: str, line_no: int) -> bool:
    """An @if / `where` predicate (expr.test - lenient on missing fields: the GUARD idiom), every
    failure located."""
    try:
        return expr.test(pred, scope)
    except ExprError as error:
        raise TempemplatorError(template, line_no, str(error)) from error
    except Exception as error:                              # the backstop: still LOCATED, never raw
        raise TempemplatorError(template, line_no, f"{type(error).__name__}: {error}") from error


def _iterate(spec: str, template: str, line_no: int, ctx: dict, schemas: dict) -> tuple:
    """The @for iterable -> (values, columns): an inclusive `<a>..<b>` integer range (rendered ends;
    no columns) or a `<table> [where <pred>]` row query over ctx['_db'] (the E3 upgrade; columns =
    every key the table's rows carry - the loop var's schema)."""
    head, tail = _split_top(spec, "..")
    if tail is not None:                                    # range: a..b, both rendered fragments
        ends = []
        for fragment in (head, tail):
            text = _render_line(fragment.strip(), template, line_no, ctx, schemas) or "0"
            try:
                value = float(text)
            except ValueError as error:                     # 'abc'
                raise TempemplatorError(template, line_no, f"range ends must be numbers: {spec!r}") from error
            if not value.is_integer():                      # nan / inf / 2.7 / a '1...3' typo (-> '.3')
                raise TempemplatorError(template, line_no,
                                        f"range ends must be whole, finite numbers: {spec!r} ({text!r})")
            ends.append(int(value))
        try:
            return list(range(ends[0], ends[1] + 1)), frozenset()
        except (OverflowError, MemoryError) as error:       # `1..1e308` (refuter round 9)
            raise TempemplatorError(template, line_no, f"range too large to iterate: {spec!r}") from error
    words = spec.split(None, 1)
    table = words[0].strip()
    pred = ""
    if len(words) > 1:
        rest = words[1].strip()
        if not rest.lower().startswith("where"):
            raise TempemplatorError(template, line_no,
                                    f"@for iterable must be `a..b` or `<table> [where <pred>]`, got {spec!r}")
        pred = rest[5:].strip()
    tables = ctx.get("_db") or {}
    if table not in tables:
        raise TempemplatorError(template, line_no,
                                f"unknown table {table!r} in @for (ctx['_db'] has {sorted(tables)})")
    rows = list(tables[table])
    columns = frozenset(key for row in rows if isinstance(row, dict) for key in row)
    if not pred:
        return rows, columns
    # the row IS the predicate's scope (where() semantics - outer fields are NOT visible)
    return [row for row in rows if _test(pred, dict(row), template, line_no)], columns


def _line_word(line: str) -> str:
    """The directive word of a line ('' for a literal line)."""
    stripped = line.strip()
    return stripped.split(None, 1)[0].lower() if stripped.startswith("@") else ""


def _opens_block(line: str) -> bool:
    """True when this directive line OPENS a nesting level: @if always, @for only in its BLOCK form
    (an inline `@for ... : body` is self-contained)."""
    word = _line_word(line)
    if word == "@if":
        return True
    if word == "@for":
        _spec, inline = _split_top(line.strip()[4:].strip(), ":")
        return inline is None
    return False


def _scan_block(lines, start, template, opener_line, *, want_else: bool, base: int = 0):
    """Scan (WITHOUT rendering - an untaken branch must never evaluate) from `start` to the @end
    matching the block opened just before it. Returns (else_index_or_None, end_index). Only a
    depth-1 @else is reported (and only when `want_else` - a @for block admits none). `base` is
    the slice's offset into the TEMPLATE, so error lines are template-absolute."""
    depth, else_at, j = 1, None, start
    while j < len(lines):
        word = _line_word(lines[j])
        if _opens_block(lines[j]):
            depth += 1
        elif word == "@else" and depth == 1:
            if not want_else:
                raise TempemplatorError(template, base + j + 1, "@else inside a @for block")
            if else_at is not None:
                raise TempemplatorError(template, base + j + 1, "a second @else in one @if")
            else_at = j
        elif word == "@end":
            depth -= 1
            if depth == 0:
                return else_at, j
        j += 1
    raise TempemplatorError(template, opener_line, "block never closed (@end missing)")


def _render_block(lines, i, template, templates, ctx, stack, schemas, base: int = 0):
    """Render `lines` from index `i` to the end (block bodies arrive pre-sliced, so terminators
    never appear here). `base` = this slice's offset into the WHOLE template, so every reported
    line number is template-absolute - a typo inside a nested block locates its REAL line
    (refuter round 5: the relative-line bug the shipped worked examples would have hit).
    `schemas` = {loop var: its table's columns} for the active loops (the column check).
    Returns (out_lines, index_after)."""
    out: list = []
    while i < len(lines):
        raw = lines[i]
        line_no = base + i + 1
        word = _line_word(raw)

        if word:
            rest = raw.strip()[len(word):].strip()

            if word in ("@end", "@else"):
                raise TempemplatorError(template, line_no, f"{word} without an open block")

            if word == "@use":
                if not rest:
                    raise TempemplatorError(template, line_no, "@use needs a template name")
                out.extend(_render_named(rest, templates, ctx, stack, (template, line_no), schemas))
                i += 1
                continue

            if word == "@if":
                cond = _test(rest, ctx, template, line_no)
                else_at, end_at = _scan_block(lines, i + 1, template, line_no, want_else=True, base=base)
                if cond:
                    branch = lines[i + 1:else_at if else_at is not None else end_at]
                    branch_base = base + i + 1
                else:
                    branch = lines[else_at + 1:end_at] if else_at is not None else []
                    branch_base = base + (else_at + 1 if else_at is not None else 0)
                rendered, _ = _render_block(branch, 0, template, templates, ctx, stack, schemas,
                                            base=branch_base)
                out.extend(rendered)
                i = end_at + 1
                continue

            if word == "@for":
                spec, inline = _split_top(rest, ":")
                head = _FOR_HEAD.match(spec.strip())
                if head is None:
                    raise TempemplatorError(template, line_no,
                                            "@for needs `$var in <a>..<b> | <table> [where <pred>]`")
                var, iterable_spec = head.group(1), head.group(2).strip()
                if inline is not None and not inline.strip():
                    raise TempemplatorError(template, line_no, "@for inline `:` with an empty body")
                if inline is not None:
                    # the inline body is carved out of THIS physical line - errors point at it
                    body_lines, after, body_base = [inline.strip()], i + 1, base + i
                else:
                    _none, end_at = _scan_block(lines, i + 1, template, line_no, want_else=False, base=base)
                    body_lines, after, body_base = lines[i + 1:end_at], end_at + 1, base + i + 1
                values, columns = _iterate(iterable_spec, template, line_no, ctx, schemas)
                had, old = (var in ctx), ctx.get(var)
                had_schema, old_schema = (var in schemas), schemas.get(var)
                schemas[var] = columns                      # the loop var's schema shadows like the var
                try:
                    for value in values:
                        ctx[var] = value
                        rendered, _ = _render_block(body_lines, 0, template, templates, ctx, stack,
                                                    schemas, base=body_base)
                        out.extend(rendered)
                finally:
                    if had:
                        ctx[var] = old
                    else:
                        ctx.pop(var, None)
                    if had_schema:
                        schemas[var] = old_schema
                    else:
                        schemas.pop(var, None)
                i = after
                continue

            raise TempemplatorError(template, line_no, f"unknown directive {word!r}")

        out.append(_render_line(raw, template, line_no, ctx, schemas))
        i += 1

    return out, i
