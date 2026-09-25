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
                                         (so `1..{$NumPhotocells}` works); $var = the integer; a
                                         BLANK end (an empty cell) means an EMPTY range - no
                                         iterations, no invented 0 (user decision 2026-09-25)
    @for $var in <table> [where <pred>]  one iteration per (matching) row of ctx["_db"][<table>];
                                         $var = the row dict (fields via $var.field); <pred> is an
                                         expr predicate evaluated with the ROW as its scope -
                                         exactly expr's where() semantics (a /regex/ in it is
                                         one literal: its `..` or `:` never splits the line)
    @for ... : <one line>                the inline body form (the line may itself be a directive)
    @if <pred> / @else / @end            block conditional (expr.test); nests freely - there is NO
                                         @elif / `@else if`: nest an @if inside the @else. The
                                         GRAMMAR is checked even in an untaken branch (only its
                                         VALUES are never evaluated)
    anything else                        a literal line - {expr} holes rendered STRICT

LITERAL BRACES (user decision 2026-09-25 - a TIA pragma needs them): a brace is written DOUBLED, the
Python format-string rule - `{{` renders `{`, `}}` renders `}` (`{{ S7_Optimized_Access := 'TRUE' }}`,
`{{ Name := '{$name}' }}`, and `{{{$x}}}` = a literal brace around a hole). A `{...}` with no brace
inside is a hole; any OTHER single brace is a located error (an extra `}` or an unclosed `{` is a
typo - never silently copied). The rule is one scanner (`_scan`), shared by the text lines, the
@for range ends, and - via `render_text` - the engine's row-template values and file targets.

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

THE STATIC LINT (`lint` / `lint_line` - the P-012 template builder's squiggles): the SAME checks,
through the same helpers and messages, walked over EVERY branch of every template without
evaluating anything - so a typo in a branch no row has taken yet is caught before one does. With a
rule's context (the fields in scope + the hook's tables) it also finds what the strict render would
raise for that rule: a missing field, an unknown loop table, a loop-column typo. Predicates stay
lenient, so an unknown name there is a WARNING (it reads blank) - as is a `where` reading its own
loop var (it sees the ROW's columns).
"""
from __future__ import annotations

import re
from collections import namedtuple

from pipeline5.language import expr
from pipeline5.language.expr import ExprError
from pipeline5.language.expr.parser import free_paths
from pipeline5.language.expr.render import _split_spec

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


def _use_problem(name: str, templates: dict, stack: tuple) -> str | None:
    """Why `name` cannot be spliced here (None = it can): an unknown name, a non-text body, a cycle,
    runaway nesting - ONE message for the renderer and the lint."""
    if name not in templates:
        return f"unknown template {name!r} (not in templates.yaml)"
    if not isinstance(templates[name], str):
        return f"template {name!r} is a ROW template (a list), not text - @use/file rendering needs a text template"
    if name in stack:
        return f"template cycle: {' -> '.join((*stack, name))}"
    if len(stack) >= _MAX_DEPTH:
        return f"@use nesting deeper than {_MAX_DEPTH}"
    return None


def _template_lines(name: str, templates: dict, stack: tuple, site: tuple) -> list:
    """Resolve a template name to its body lines (`_use_problem` guards it). `site` = (template,
    line) of the referencing @use, for located errors."""
    problem = _use_problem(name, templates, stack)
    if problem:
        raise TempemplatorError(*site, problem)
    return templates[name].splitlines()


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
    for kind, start, end in _scan(line):                   # the SAME holes the render sees (a doubled-
        if kind != "hole":                                  # brace literal is no hole; a lone brace is
            continue                                        # the render's error)
        for path in expr.hole_paths(line[start + 1:end - 1]) or ():   # PARSED: a data-function
            head, _dot, rest = path.partition(".")          # predicate's row column / a let-bound name
            if rest and head in schemas:                    # is not a loop row's column (refuter round 9)
                problem = _column_problem(head, rest.split(".", 1)[0], schemas[head])
                if problem:
                    raise TempemplatorError(template, line_no, problem)


def _column_problem(head: str, column: str, columns) -> str | None:
    """The loop-column verdict for `$head.column` (None = a real column) - ONE message for the
    renderer and the lint."""
    if column in columns:
        return None
    known = ", ".join(sorted(columns)) or "none - a range variable is a number"
    return f"${head}.{column}: the loop's table has no column {column!r} (columns: {known})"


def _scan(text: str):
    """The ONE brace scanner, LEFT TO RIGHT (a blind replace breaks `{{{$x}}}`): yields (kind, start,
    end) runs covering `text` - "hole" = a `{...}` with no brace inside (expr's hole shape), "brace" =
    a doubled `{{` / `}}` (ONE literal brace), "lone" = a single brace that opens or closes no hole (an
    authoring error), "text" = everything else. Braces pair LEFT TO RIGHT, as in a Python format
    string: `{{$x}}` is the literal text `{$x}`, `{{{$x}}}` a literal brace around a hole."""
    i = start = 0
    while i < len(text):
        ch = text[i]
        if ch not in "{}":
            i += 1
            continue
        if i > start:
            yield "text", start, i
        hole = _HOLE.match(text, i)                         # (anchored on a `{` - None at a `}`)
        if text.startswith(ch * 2, i):
            yield "brace", i, i + 2
            i += 2
        elif hole:
            yield "hole", i, hole.end()
            i = hole.end()
        else:
            yield "lone", i, i + 1
            i += 1
        start = i
    if start < len(text):
        yield "text", start, len(text)


def _lone_brace(text: str, at: int) -> ExprError:
    brace = text[at]
    line = text.count("\n", 0, at) + 1                    # a multi-line row value: line + column
    column = at - text.rfind("\n", 0, at)                  # (1-based; rfind -1 on the first line)
    where = f"column {column}" if line == 1 else f"line {line}, column {column}"
    return ExprError(f"a lone {brace!r} at {where} of {text!r} - write a literal brace doubled "
                     f"({brace * 2!r}); a {{hole}} cannot contain a brace")


def render_text(text: str, ctx: dict) -> str:
    """ONE line / value rendered the Tempemplator way: `{{` / `}}` literal braces + STRICT `{expr}`
    holes, each hole rendered on its own (a literal brace can never pair up into a hole). Raises
    expr's ExprError. The engine's row-template values and file targets render through this too -
    the brace rule is the same wherever a template renders."""
    out = []
    for kind, start, end in _scan(text):
        if kind == "lone":
            raise _lone_brace(text, start)
        if kind == "hole":
            out.append(expr.render(text[start:end], ctx, mode="strict"))
        else:
            out.append(text[start] if kind == "brace" else text[start:end])
    return "".join(out)


def _render_line(line: str, template: str, line_no: int, ctx: dict, schemas: dict) -> str:
    """A literal line: render its {expr} holes STRICT (a missing field / bad expr is an authoring
    error the engine must surface as a finding, never a silent blank); `{{` / `}}` are literal braces."""
    try:
        if schemas:
            _check_loop_columns(line, template, line_no, schemas)
        return render_text(line, ctx)
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
        if not head.strip() or not tail.strip():            # `..3` - a syntax slip, not blank data
            raise TempemplatorError(template, line_no, f"a range end is missing: {spec!r}")
        texts = [_render_line(fragment.strip(), template, line_no, ctx, schemas).strip() for fragment in (head, tail)]
        ends = []
        for text in texts:                                  # EVERY non-blank end is validated first - a
            try:                                            # malformed end is an error even beside a blank one
                ends.append(_end_value(text, spec))
            except ValueError as error:
                raise TempemplatorError(template, line_no, str(error)) from error
        if None in ends:                                    # a BLANK end (an empty cell) = an EMPTY range - no
            return [], frozenset()                          # iterations (user decision 2026-09-25; it used to
        try:                                                # read as 0 and invent an iteration - refuter round 10)
            return list(range(ends[0], ends[1] + 1)), frozenset()
        except (OverflowError, MemoryError) as error:       # `1..1e308` (refuter round 9)
            raise TempemplatorError(template, line_no, f"range too large to iterate: {spec!r}") from error
    words = spec.split(None, 1)                             # `<table> [where <pred>]` - the shape is
    table = words[0].strip()                                # grammar-checked by _check_directive
    pred = words[1].strip()[5:].strip() if len(words) > 1 else ""
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


def _end_value(text: str, spec: str):
    """One RENDERED range end -> its int; None for a BLANK end (an empty range). Raises ValueError
    carrying the message - ONE for the renderer and the lint."""
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:                                      # 'abc'
        raise ValueError(f"range ends must be numbers: {spec!r}") from None
    if not value.is_integer():                              # nan / inf / 2.7 / a '1...3' typo (-> '.3')
        raise ValueError(f"range ends must be whole, finite numbers: {spec!r} ({text!r})")
    return int(value)


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


_DIRECTIVES = ("@use", "@for", "@if", "@else", "@end")


def _check_directive(raw: str, word: str, template: str, line_no: int) -> None:
    """A directive line's GRAMMAR - checked when the line is rendered AND when a block is scanned, so
    a slip inside an UNTAKEN branch is still a located error: laziness is about VALUES, never about
    grammar (refuter round 12: `@else if <pred>` read as a bare @else - its condition silently
    dropped, the wrong branch rendered - and an `@elif` inside an untaken branch was never seen)."""
    rest = raw.strip()[len(word):].strip()
    if word not in _DIRECTIVES:
        raise TempemplatorError(template, line_no, f"unknown directive {word!r} (the directives: "
                                f"{', '.join(_DIRECTIVES)} - there is no @elif: nest an @if inside the @else)")
    if word in ("@else", "@end") and rest:
        raise TempemplatorError(template, line_no, f"{word} takes nothing after it (got {rest!r}) - there "
                                "is no `@else if`: nest an @if inside the @else")
    if word == "@if" and not rest:
        raise TempemplatorError(template, line_no, "@if needs a condition")
    if word == "@use" and not rest:
        raise TempemplatorError(template, line_no, "@use needs a template name")
    if word == "@for":
        spec, inline = _split_top(rest, ":")
        head = _FOR_HEAD.match(spec.strip())
        if head is None:
            raise TempemplatorError(template, line_no, "@for needs `$var in <a>..<b> | <table> [where <pred>]`")
        iterable = head.group(2).strip()
        if _split_top(iterable, "..")[1] is None:            # the TABLE form
            words = iterable.split(None, 1)
            if len(words) > 1:
                tail = words[1].strip()
                if not re.match(r"where(\s|$)", tail, re.IGNORECASE):   # the WORD `where` (not `wherever`)
                    raise TempemplatorError(template, line_no, f"@for iterable must be `a..b` or "
                                            f"`<table> [where <pred>]`, got {iterable!r}")
                if not tail[5:].strip():                     # a dangling `where` - not "every row"
                    raise TempemplatorError(template, line_no, "a `where` needs a predicate")
        if inline is not None:
            body = inline.strip()
            if not body:
                raise TempemplatorError(template, line_no, "@for inline `:` with an empty body")
            inner = _line_word(body)
            if inner in ("@if", "@else", "@end") or (inner == "@for" and _opens_block(body)):
                raise TempemplatorError(template, line_no, f"an inline @for body cannot be a block "
                                        f"directive ({inner}) - use the block form with @end")
            if inner:                                        # an inline body that is itself a directive
                _check_directive(body, inner, template, line_no)


def _scan_block(lines, start, template, opener_line, *, want_else: bool, base: int = 0):
    """Scan (WITHOUT rendering - an untaken branch must never evaluate) from `start` to the @end
    matching the block opened just before it. Returns (else_index_or_None, end_index). Only a
    depth-1 @else is reported (and only when `want_else` - a @for block admits none). `base` is
    the slice's offset into the TEMPLATE, so error lines are template-absolute. Every directive
    line it passes is GRAMMAR-checked (never evaluated)."""
    # one entry per OPEN block, innermost last: [kind, else_seen, line] - the structure is checked at
    # EVERY depth (refuter round 13: a misplaced @else in a NESTED block of an untaken branch passed)
    stack = [["@if" if want_else else "@for", False, opener_line]]
    else_at, j = None, start
    while j < len(lines):
        word = _line_word(lines[j])
        line_no = base + j + 1
        if word:
            _check_directive(lines[j], word, template, line_no)
        if _opens_block(lines[j]):
            stack.append([word, False, line_no])
        elif word == "@else":
            kind, seen, _line = stack[-1]
            if kind != "@if":
                raise TempemplatorError(template, line_no, "@else inside a @for block")
            if seen:
                raise TempemplatorError(template, line_no, "a second @else in one @if")
            stack[-1][1] = True
            if len(stack) == 1:
                else_at = j
        elif word == "@end":
            stack.pop()
            if not stack:
                return else_at, j
        j += 1
    kind, _seen, line = stack[-1]                            # the INNERMOST unclosed block is the culprit
    raise TempemplatorError(template, line, f"block never closed (the {kind} here has no @end)")


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
            _check_directive(raw, word, template, line_no)
            rest = raw.strip()[len(word):].strip()

            if word in ("@end", "@else"):
                raise TempemplatorError(template, line_no, f"{word} without an open block")

            if word == "@use":
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
                head = _FOR_HEAD.match(spec.strip())            # grammar-checked by _check_directive above
                var, iterable_spec = head.group(1), head.group(2).strip()
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

        out.append(_render_line(raw, template, line_no, ctx, schemas))
        i += 1

    return out, i


# --- the STATIC lint (P-012: the template builder's squiggles) ------------------------------------ #
# One problem the renderer would raise - or, as a WARNING, a lenient read that silently yields blank -
# found WITHOUT rendering. `where` = a TEXT template's 1-based line (the engine uses (entry, field) for
# a ROW template's value, None for a whole entry); `start` / `end` = 0-based columns in that line.
Problem = namedtuple("Problem", "template where start end message severity")


def _field_span(text: str, start: int, end: int, name: str) -> tuple:
    """The span of the first `$name` reference (`name` may be dotted: `r.tagg`) inside text[start:end]
    - the whole run when none is found."""
    found = re.compile(r"\$" + re.escape(name) + r"(?!\w)").search(text, start, end)
    return (found.start(), found.end()) if found else (start, end)


def lint_line(text: str, *, fields=None, loops=None) -> list:
    """ONE literal line / row value judged the way `render_text` and the loop-column check judge it -
    WITHOUT rendering: [(start, end, message, severity)], columns into `text`. `fields` = the
    top-level names in scope (None = unknown - the strict missing-field check is skipped); `loops` =
    {loop var: its table's columns - empty for a range var, None when unknown}."""
    loops = loops or {}
    names = None if fields is None else set(fields) | set(loops)
    issues = []
    runs = list(_scan(text))
    for index, (kind, start, end) in enumerate(runs):
        if kind == "lone":
            issues.append((start, end, str(_lone_brace(text, start)), "error"))
        elif kind == "hole" and not text[start + 1:end - 1].strip():  # {} renders "" (expr's empty hole) -
            issues.append((start, end, "an empty hole renders nothing - a literal {} is written {{}}",
                           "warning"))                               # an empty JSON object silently lost
        elif kind == "text" and text[start] == "$" and _braced(text, runs, index):
            literal = "{" + text[start:end] + "}"               # `{{$x}}` = the literal text `{$x}`
            issues.append((runs[index - 1][1], runs[index + 1][2], "renders the literal text " + literal
                           + " - braces around a hole are written {{" + literal + "}}", "warning"))
        elif kind == "hole":
            expression, spec = _split_spec(text[start + 1:end - 1])
            if spec is not None and not expression.strip():     # `{:03d}` - the render compiles ""
                issues.append((start, end, f"a hole needs an expression before its format spec ':{spec}' "
                                           "(the render fails)", "error"))
                continue
            syntax = expr.check_template(text[start:end])
            issues.extend((start + i.start, start + i.end, i.message, "error") for i in syntax)
            if syntax:
                continue                                    # malformed: its fields cannot be read
            problem = _spec_problem(spec) if spec is not None else None
            if problem:
                issues.append((end - 1 - len(spec), end - 1, problem, "error"))
            for path in sorted(expr.hole_paths(text[start + 1:end - 1]) or ()):
                head, _dot, rest = path.partition(".")
                if names is not None and head not in names:
                    message = f"missing field ${head} - not in scope here (the strict render raises)"
                elif rest and loops.get(head) is not None:
                    message = _column_problem(head, rest.split(".", 1)[0], loops[head])
                    head = f"{head}.{rest.split('.', 1)[0]}"      # squiggle the whole `$var.column`
                else:
                    message = None
                issue = (*_field_span(text, start, end, head), message, "error")
                if message and issue not in issues:
                    issues.append(issue)
    return issues


def _spec_problem(spec: str) -> str | None:
    """Why NO value can satisfy a hole's format spec (None = some can) - tried with the kinds of value
    `format_spec` coerces to: an int for d/x/X/o/b/c/n, a float for e/E/f/F/g/G/%, else a text AND a
    number (an untyped spec formats the value as it is - a field's text, a loop's number)."""
    from pipeline5.language.expr.runtime import _FLOAT_CONV, _INT_CONV
    last = spec[-1:]
    samples = [7] if last and last in _INT_CONV else [7.5] if last and last in _FLOAT_CONV else ["x", 7]
    first = None
    for sample in samples:
        try:
            format(sample, spec)
            return None
        except (ValueError, TypeError, OverflowError) as error:
            first = first or error
    return f"bad format spec {spec!r}: {first}"


def _braced(text: str, runs: list, index: int) -> bool:
    """True when runs[index] sits between a doubled `{{` and a doubled `}}` (Python's pairing makes
    `{{$x}}` literal text - likely meant as `{{{$x}}}`)."""
    return (0 < index < len(runs) - 1 and runs[index - 1][0] == runs[index + 1][0] == "brace"
            and text[runs[index - 1][1]] == "{" and text[runs[index + 1][1]] == "}")


def lint(templates: dict, *, start: str | None = None, fields=None, tables=None) -> list:
    """Every problem the renderer would raise for the TEXT templates in `templates`, found WITHOUT
    rendering - EVERY branch of every template (a render evaluates only the taken one). `start` +
    `fields` = a rule's context: that template - and whatever it @uses, loop vars carried - is walked
    with `fields` (the matched row's columns + the E1 names) in scope, so a missing field is an error
    exactly where the strict render raises; every template is also walked without a context (the
    data-independent checks). `tables` = {table: columns} of the rule's hook database, for the context
    walk: an unknown loop table, the loop-column check, a `where` predicate's names. Returns
    [Problem], each once."""
    found = {}

    def add(template, line, start_col, end_col, message, severity="error"):
        found.setdefault((template, line, start_col, end_col, message),
                         Problem(template, line, start_col, end_col, message, severity))

    if start is not None and isinstance(templates.get(start), str):      # the context walk
        _Lint(templates, tables, add).named(start, None if fields is None else frozenset(fields), {}, ())
    plain = _Lint(templates, None, add)                 # every template, no context: another
    for name, body in templates.items():               # rule (another hook) may use it
        if isinstance(body, str):
            plain.named(name, None, {}, ())
    for name, line, span, depth in _deep_chains(templates):   # the memo walk above sees each template
        add(name, line, *span, f"@use nesting deeper than {_MAX_DEPTH} (a chain of {depth} templates "
                               "starts here - the render stops at the limit)")   # once: depth apart
    return list(found.values())


def use_refs(body: str) -> list:
    """(line, (start, end), name) of every @use in a text template - inline @for bodies included."""
    refs = []
    for number, line in enumerate(body.splitlines(), start=1):
        for role, start, end in outline(line):
            if role == "ref":
                refs.append((number, (start, end), line[start:end]))
            elif role == "body":
                refs += [(number, (start + s, start + e), line[start + s:start + e])
                         for inner, s, e in outline(line[start:end]) if inner == "ref"]
    return refs


def _deep_chains(templates: dict) -> list:
    """(template, line, span, depth) - each text template whose LONGEST @use chain splices more templates
    than the renderer allows, located at the @use that starts it (a cycle is cut: the cycle check
    reports it)."""
    depths, active = {}, set()

    def depth(name):
        if name in depths:
            return depths[name]
        if name in active or not isinstance(templates.get(name), str):
            return 0
        active.add(name)
        best = 1 + max((depth(ref) for _line, _span, ref in use_refs(templates[name])), default=0)
        active.discard(name)
        depths[name] = best
        return best

    out = []
    for name, body in templates.items():
        if not isinstance(body, str):
            continue
        try:
            total = depth(name)
        except RecursionError:                           # thousands deep: far past the limit anyway
            total = _MAX_DEPTH + 1
        if total > _MAX_DEPTH:
            refs = use_refs(body)
            line, span, _ref = max(refs, key=lambda ref: depths.get(ref[2], 0)) if refs else (1, (0, 0), "")
            out.append((name, line, span, total))
    return out


def _block_extent(lines, start: int, hi: int, want_else: bool) -> tuple:
    """The STRUCTURE of the block opened just before `start` (within lines[:hi]) - grammar is the
    walker's job, line by line: (else_at, end_at, innermost, problems). end_at None = never closed,
    and `innermost` = the innermost unclosed opener's index (the renderer's culprit); `problems` =
    this block's own misplaced / second @else as (index, message) - a nested block reports its own."""
    stack = [["@if" if want_else else "@for", False, start - 1]]
    else_at, problems = None, []
    for j in range(start, hi):
        word = _line_word(lines[j])
        if _opens_block(lines[j]):
            stack.append([word, False, j])
        elif word == "@else":
            kind, seen, _at = stack[-1]
            if len(stack) == 1:
                if kind != "@if":
                    problems.append((j, "@else inside a @for block"))
                elif seen:
                    problems.append((j, "a second @else in one @if"))
                else:
                    else_at = j
            stack[-1][1] = True
        elif word == "@end":
            stack.pop()
            if not stack:
                return else_at, j, None, problems
    return else_at, None, stack[-1][2], problems


def _whole(raw: str, col: int) -> tuple:
    """The span of a line's text (its indentation excluded)."""
    return col + len(raw) - len(raw.lstrip()), col + len(raw.rstrip())


class _Lint:
    """The lint walk: the renderer's structure over EVERY branch - lines checked, nothing evaluated.
    `fields` = the names in scope (a frozenset, None = no context); `loops` = {var: columns}."""

    def __init__(self, templates: dict, tables, add):
        self.templates, self.tables, self.add, self.seen = templates, tables, add, set()

    def named(self, name, fields, loops, stack):
        key = (name, fields, frozenset(loops.items()))
        if key in self.seen:                                # one walk per (template, context)
            return
        self.seen.add(key)
        lines = self.templates[name].splitlines()
        self.block(lines, 0, len(lines), name, fields, loops, (*stack, name), 0, 0, frozenset())

    def block(self, lines, lo, hi, template, fields, loops, stack, base, col, skip):
        """lines[lo:hi]; `base` / `col` place them in the template (an inline @for body is carved out
        of its @for line); `skip` = @else lines the enclosing structure already judged."""
        i = lo
        while i < hi:
            word = _line_word(lines[i])
            if word and i not in skip:
                i = self.directive(lines, i, hi, word, template, fields, loops, stack, base, col)
                continue
            if not word:
                for s, e, message, severity in lint_line(lines[i], fields=fields, loops=loops):
                    self.add(template, base + i + 1, col + s, col + e, message, severity)
            i += 1

    def grammar(self, lines, j, template, base, col):
        """A directive line's grammar (`_check_directive`) - an error, never a stop."""
        try:
            _check_directive(lines[j], _line_word(lines[j]), template, base + j + 1)
        except TempemplatorError as error:
            self.add(template, base + j + 1, *_whole(lines[j], col), error.message)

    def directive(self, lines, i, hi, word, template, fields, loops, stack, base, col):
        raw, line_no = lines[i], base + i + 1
        lead = len(raw) - len(raw.lstrip())
        self.grammar(lines, i, template, base, col)
        rest = raw.strip()[len(word):].strip()
        at = col + (raw.find(rest, lead + len(word)) if rest else len(raw))
        if word in ("@else", "@end"):
            self.add(template, line_no, *_whole(raw, col), f"{word} without an open block")
        elif word == "@use" and rest:
            problem = _use_problem(rest, self.templates, stack)
            if problem:
                self.add(template, line_no, at, at + len(rest), problem)
            else:
                self.named(rest, fields, loops, stack)
        elif word == "@if":
            if rest:
                names = None if fields is None else set(fields) | set(loops)
                self.predicate(rest, template, line_no, at, names, loops=loops)
            return self.structure(lines, i, hi, template, fields, loops, stack, base, col, "@if", loops)
        elif word == "@for":
            return self.loop(lines, i, hi, rest, at, template, fields, loops, stack, base, col)
        return i + 1

    def structure(self, lines, i, hi, template, fields, loops, stack, base, col, kind, body_loops):
        """An @if / a block @for: its extent + structural problems, then EVERY branch walked."""
        else_at, end_at, innermost, problems = _block_extent(lines, i + 1, hi, want_else=kind == "@if")
        for j, message in problems:
            self.add(template, base + j + 1, *_whole(lines[j], col), message)
        for j in {else_at, end_at, *(j for j, _message in problems)} - {None}:
            self.grammar(lines, j, template, base, col)     # the boundary lines no branch walks
        if end_at is None:
            if innermost == i:                              # only the INNERMOST unclosed block is the culprit
                self.add(template, base + i + 1, *_whole(lines[i], col),
                         f"block never closed (the {kind} here has no @end)")
            end_at = hi
        judged = frozenset(j for j, _message in problems)
        first_hi = else_at if else_at is not None else end_at
        self.block(lines, i + 1, first_hi, template, fields, body_loops, stack, base, col, judged)
        if else_at is not None:
            self.block(lines, else_at + 1, end_at, template, fields, body_loops, stack, base, col, judged)
        return end_at + 1

    def loop(self, lines, i, hi, rest, at, template, fields, loops, stack, base, col):
        spec, inline = _split_top(rest, ":")
        head = _FOR_HEAD.match(spec.strip())
        inner = dict(loops)
        if head is not None:                                # (a malformed head was reported above)
            iterable_at = at + len(spec) - len(spec.lstrip()) + head.start(2)
            inner[head.group(1)] = self.iterable(head.group(2).strip(), iterable_at, head.group(1),
                                                 template, base + i + 1, fields, loops)
        if inline is None:
            return self.structure(lines, i, hi, template, fields, loops, stack, base, col, "@for", inner)
        body, word = inline.strip(), _line_word(inline)
        if body and word not in ("@if", "@else", "@end") and not (word == "@for" and _opens_block(body)):
            body_at = at + len(spec) + 1 + len(inline) - len(inline.lstrip())
            self.block([body], 0, 1, template, fields, inner, stack, base + i, body_at, frozenset())
        return i + 1

    def iterable(self, iterable, at, var, template, line_no, fields, loops):
        """The @for iterable checked as `_iterate` would judge it -> the loop var's columns (empty for
        a range var, None when the table's columns are unknown)."""
        low, high = _split_top(iterable, "..")
        if high is not None:
            if not low.strip() or not high.strip():
                self.add(template, line_no, at, at + len(iterable), f"a range end is missing: {iterable!r}")
                return frozenset()
            for fragment, offset in ((low, 0), (high, len(low) + 2)):
                text = fragment.strip()
                where = at + offset + len(fragment) - len(fragment.lstrip())
                issues = lint_line(text, fields=fields, loops=loops)
                for s, e, message, severity in issues:
                    self.add(template, line_no, where + s, where + e, message, severity)
                if not issues and all(kind != "hole" for kind, _s, _e in _scan(text)):
                    try:                                    # a LITERAL end: judged now, not at render
                        _end_value(render_text(text, {}), iterable)
                    except ValueError as error:
                        self.add(template, line_no, where, where + len(text), str(error))
            return frozenset()
        words = iterable.split(None, 1)
        table, columns = words[0], None
        if self.tables is not None:
            if table in self.tables:
                columns = frozenset(self.tables[table])
            else:
                self.add(template, line_no, at, at + len(table),
                         f"unknown table {table!r} in @for (the database at this hook has {sorted(self.tables)})")
        tail = words[1].strip() if len(words) > 1 else ""
        pred = tail[5:].strip() if re.match(r"where(\s|$)", tail, re.IGNORECASE) else ""
        if pred:                                            # the ROW is its scope (where() semantics)
            self.predicate(pred, template, line_no, at + len(iterable) - len(pred), columns, var, table)
        return columns

    def predicate(self, pred, template, line_no, at, names, loop_var=None, table=None, loops=None):
        """An @if / `where` predicate: its syntax (an error - expr.test raises) and what it reads, where
        that is known - a WARNING (a predicate is lenient: an unknown name, or a loop row's missing
        column in an @if, reads blank - the branch is silently never taken)."""
        syntax = expr.check(pred)
        for issue in syntax:
            self.add(template, line_no, at + issue.start, at + issue.end, issue.message)
        if syntax:
            return
        for path in sorted(free_paths(pred) or ()) if table is None and loops else ():
            head, _dot, rest = path.partition(".")
            if rest and loops.get(head) is not None:
                column = rest.split(".", 1)[0]
                problem = _column_problem(head, column, loops[head])
                if problem:
                    s, e = _field_span(pred, 0, len(pred), f"{head}.{column}")
                    self.add(template, line_no, at + s, at + e, f"{problem} - the @if reads it as blank", "warning")
        if names is None:
            return
        for head in sorted({path.split(".", 1)[0] for path in free_paths(pred) or ()} - set(names)):
            if table is None:
                message = f"${head} is not in scope here - the @if reads it as blank"
            elif head == loop_var:
                message = (f"a `where` sees each {table} ROW's columns - ${head} is the loop variable "
                           "itself (name the column directly)")
            else:
                message = f"${head} is not a column of {table} - the `where` reads it as blank"
            s, e = _field_span(pred, 0, len(pred), head)
            self.add(template, line_no, at + s, at + e, message, "warning")


# --- the grammar's views for the builder's highlighter (P-012) ------------------------------------ #
def brace_runs(text: str) -> list:
    """The brace scanner's runs over `text` - (kind, start, end), kind in hole / brace / lone / text:
    the builder colours exactly what the renderer will see."""
    return list(_scan(text))


def hole_parts(body: str) -> tuple:
    """A hole's body -> (expression, format spec or None), split exactly as render splits it (the
    LAST top-level ':' - never one inside a string, a /regex/ or a call's arguments)."""
    return _split_spec(body)


def outline(line: str) -> list:
    """The syntactic parts of ONE template line as (role, start, end) columns - the builder reads the
    grammar here instead of re-deriving it. Roles: directive (the @word), ref (an @use name), var (a
    @for var, `$` included), keyword (`in` / `where`), table, predicate (an @if / `where` expression),
    fragment (a range end - text with holes), body (an inline @for body - a line itself: outline it
    again), text (a literal line - text with holes). A malformed directive outlines as far as it parses."""
    word = _line_word(line)
    if not word:
        return [("text", 0, len(line))]
    lead = len(line) - len(line.lstrip())
    parts = [("directive", lead, lead + len(word))]
    rest = line.strip()[len(word):].strip()
    if not rest:
        return parts
    at = line.find(rest, lead + len(word))
    if word == "@use":
        parts.append(("ref", at, at + len(rest)))
    elif word == "@if":
        parts.append(("predicate", at, at + len(rest)))
    elif word == "@for":
        spec, inline = _split_top(rest, ":")
        head = _FOR_HEAD.match(spec)
        if head is not None:
            parts.append(("var", at + head.start(1) - 1, at + head.end(1)))
            keyword = at + spec.lower().find("in", head.end(1))
            parts.append(("keyword", keyword, keyword + 2))
            iterable, start = head.group(2).rstrip(), at + head.start(2)
            low, high = _split_top(iterable, "..")
            if high is not None:
                parts.append(("fragment", start, start + len(low)))
                parts.append(("fragment", start + len(low) + 2, start + len(iterable)))
            else:
                words = iterable.split(None, 1)
                parts.append(("table", start, start + len(words[0])))
                tail = words[1] if len(words) > 1 else ""
                if re.match(r"where(\s|$)", tail, re.IGNORECASE):
                    where = start + iterable.find(tail, len(words[0]))
                    parts.append(("keyword", where, where + 5))
                    pred = tail[5:].strip()
                    if pred:
                        parts.append(("predicate", start + len(iterable) - len(pred), start + len(iterable)))
        if inline is not None and inline.strip():
            body = at + len(spec) + 1 + len(inline) - len(inline.lstrip())
            parts.append(("body", body, body + len(inline.strip())))
    return parts

