"""The templates.yaml EDITING MODEL behind the Files tab's template mode (C-025) - Tk-free and tested;
src://pipeline5/workbench/template_mode.py is the view over it.

A `chain_reactions/templates.yaml` is ONE YAML mapping of named templates: a TEXT template (a block
scalar - the `file` action) or a ROW template (a list of {field: template} maps - `add_rows`). This
module reads the document exactly as the engine does (the same loader: a YAML error here is the
engine's rx_templates_unreadable) and remembers WHERE every template line and row value sits, so the
builder can:

    parse(text)                  -> Doc: the engine's view (`templates`) + every scalar's position
    spans(doc, language)         two-layer highlighting - the system's target language (its
                                 `template_language`) UNDER the template constructs (@directives,
                                 @use references, {holes} and their expression tokens, {{ }} braces);
                                 YAML for the structure
    place(doc, problems)         the engine's lint problems (engine.lint) -> document offsets + labels
    completions(doc, at, ctx)    what fits at the cursor: the rule's columns, loop vars and _params
                                 keys after `$` (a `where` sees the loop table's columns only), a loop
                                 row's columns after `$var.`, templates after `@use`, tables in
                                 `@for ... in`, directives after `@`, functions
    Session                      the live context: the rules, the Database each hook's fire gets
                                 (the run-plan modelled - see its docstring), lint + preview

POSITIONS are exact for literal blocks (`|`, `|-`, `|+`, with or without an indentation indicator),
plain scalars and single-line quoted scalars (escapes decoded); a FOLDED block (`>`) or a multi-line
quoted scalar joins lines, so its positions are approximate. The grammar is never re-derived here:
lines are read through the renderer's own views (tempemplator.outline / brace_runs / hole_parts /
use_refs - src://pipeline5/language/tempemplator.py).
"""
from __future__ import annotations

import os
import re
import threading
from dataclasses import dataclass, field

from pipeline5.language import expr
from pipeline5.language import tempemplator
from pipeline5.workbench import syntax_highlight as highlight

# the template layer's tags -> (dark, light) colours; the view raises them over the language layers
TAG_COLORS = {
    "tp_directive": ("#e67e22", "#b3541e"),    # @use @for @if @else @end, `in`, `where`
    "tp_ref":       ("#00cec9", "#00838f"),    # an @use'd template name
    "tp_table":     ("#81ecec", "#00796b"),    # a @for table
    "tp_hole":      ("#fd79a8", "#c2185b"),    # the { } of a hole
    "tp_literal":   ("#b2bec3", "#6e7a8a"),    # a doubled {{ / }} (one literal brace)
    "tp_spec":      ("#fdcb6e", "#c05c00"),    # a hole's :format spec
    "tx_field":     ("#74b9ff", "#0055cc"),    # the expression tokens (the ƒx builder's palette)
    "tx_func":      ("#a29bfe", "#7040a0"),
    "tx_data_func": ("#a29bfe", "#7040a0"),
    "tx_keyword":   ("#e67e22", "#b3541e"),
    "tx_string":    ("#55efc4", "#1a7e1a"),
    "tx_regex":     ("#ff7675", "#b33939"),
    "tx_number":    ("#fdcb6e", "#c05c00"),
    "tx_error":     ("#ff6b6b", "#d63031"),
}
_ROLE_TAGS = {"directive": "tp_directive", "ref": "tp_ref", "var": "tx_field", "keyword": "tp_directive",
              "table": "tp_table"}
_DIRECTIVES = ("@use", "@for", "@if", "@else", "@end")


@dataclass
class Scalar:
    """Where one YAML scalar's CONTENT sits: the document offset of each content line's first column
    (`starts`) - or, for a single-line QUOTED scalar, of each of its value's characters (`chars`, the
    escapes decoded; one more for the end). `exact` False = a folded block / a multi-line quoted
    scalar (positions approximate)."""
    starts: list
    exact: bool = True
    chars: list | None = None
    value: str = ""                             # the decoded value - a chars scalar's lines map through it

    def first_line(self, text: str) -> tuple:
        """(start, end) of the scalar's first document line - where an APPROXIMATE position is shown."""
        start = self.starts[0] if self.chars is None else self.chars[0]
        end = text.find("\n", start)
        return start, len(text) if end == -1 else end

    def offset(self, line: int, column: int) -> int:
        """(0-based content line, column) -> the document offset."""
        if self.chars is not None:                  # a quoted scalar: its `\n` escapes are value lines
            index = sum(len(piece) + 1 for piece in self.value.split("\n")[:line]) + max(0, column)
            return self.chars[max(0, min(index, len(self.chars) - 1))]
        return self.starts[max(0, min(line, len(self.starts) - 1))] + max(0, column)

    def at(self, index: int, value: str) -> int:
        """A character offset into the scalar's VALUE -> the document offset."""
        if self.chars is not None:
            return self.chars[max(0, min(index, len(self.chars) - 1))]
        line = value.count("\n", 0, index)
        return self.offset(line, index - (value.rfind("\n", 0, index) + 1))

    def end(self, value: str) -> int:
        """The document offset just past the value's LAST non-blank line (a `|` / `|+` block's trailing
        newlines are not content the document shows as the block's)."""
        lines = value.split("\n")
        last = max((k for k, line in enumerate(lines) if line.strip()), default=0)
        return self.offset(last, len(lines[last])) if self.chars is None else self.chars[-1]


@dataclass
class Entry:
    name: str                                   # the template's name, as text (YAML may type it: 123)
    kind: str                                   # "text" | "row" | "other"
    key: tuple                                  # (start, end) of the name
    body: Scalar | None = None                  # text: the block's content lines
    text: str = ""                              # text: the template itself
    values: dict = field(default_factory=dict)  # row: {(entry number, field): Scalar}
    value_text: dict = field(default_factory=dict)  # row: {(entry number, field): the value}


@dataclass
class Doc:
    text: str
    templates: dict                             # the engine's view ({} when the YAML does not load)
    entries: dict                               # name (text) -> Entry
    error: tuple | None = None                  # (offset, message): the engine's rx_templates_unreadable


@dataclass
class Placed:
    """One problem on the document: (start, end) offsets (None = no position - a RULE problem),
    the message, its severity, and the problems list's locator label."""
    start: int | None
    end: int | None
    message: str
    severity: str
    label: str


@dataclass
class Context:
    """What the cursor's completions may offer beyond the document itself - the chosen rule's view."""
    fields: frozenset | None = None             # the matched row's columns (None = no rule chosen)
    tables: dict | None = None                  # {table: columns} at the rule's hook
    params: dict = field(default_factory=dict)  # the project params ($_params. completion)
    reach: frozenset | None = None              # the templates the rule renders (None = every one)


# --- parse ---------------------------------------------------------------------------------------- #
def _line_starts(text: str) -> list:
    starts = [0]
    for match in re.finditer("\n", text):
        starts.append(match.end())
    return starts


def _row(text: str, starts: list, index: int) -> str:
    end = starts[index + 1] if index + 1 < len(starts) else len(text)
    return text[starts[index]:end].rstrip("\n").rstrip("\r")


def parse(text: str) -> Doc:
    """The document as the engine loads it (the safe loader - config.params._read_yaml) + WHERE each
    template sits (a round-trip parse's line/column marks). Names and field keys are kept as TEXT -
    YAML types `123:` / `true:` keys, the positions must not care."""
    from ruamel.yaml import YAML
    starts = _line_starts(text)

    def offset(line, column):
        return starts[min(line, len(starts) - 1)] + column

    try:
        templates = YAML(typ="safe").load(text) or {}
    except Exception as error:  # noqa: BLE001 - any loader failure is the engine's unreadable file
        mark = getattr(error, "problem_mark", None) or getattr(error, "context_mark", None)
        where = offset(mark.line, mark.column) if mark is not None else 0
        return Doc(text, {}, {}, (min(where, len(text)), f"templates.yaml does not load: {error}"))
    if not isinstance(templates, dict):
        return Doc(text, {}, {}, (0, "templates.yaml must be a mapping of named templates"))
    try:
        tree = YAML().load(text)
    except Exception:  # noqa: BLE001 - the safe load passed; positions are a convenience
        tree = None
    entries = {}
    for raw_name, body in templates.items():
        name = str(raw_name)
        key_line, key_col = _mark(tree, "key", raw_name)
        key = (offset(key_line, key_col), offset(key_line, key_col) + len(name)) if key_line is not None else (0, 0)
        if isinstance(body, str):
            line, col = _mark(tree, "value", raw_name)
            scalar = _scalar(text, starts, line, col, body) if line is not None else None
            entries[name] = Entry(name, "text", key, body=scalar, text=body)
        elif isinstance(body, list):
            entry = Entry(name, "row", key)
            items = _child(tree, raw_name)
            for number, spec in enumerate(body, start=1):
                item = items[number - 1] if items is not None and number - 1 < len(items) else None
                if not isinstance(spec, dict) or not hasattr(item, "lc"):
                    continue
                for column, value in spec.items():
                    if isinstance(value, str):
                        line, col = _mark(item, "value", column)
                        entry.value_text[(number, str(column))] = value
                        if line is not None:
                            entry.values[(number, str(column))] = _scalar(text, starts, line, col, value)
            entries[name] = entry
        else:
            entries[name] = Entry(name, "other", key)
    return Doc(text, templates, entries)


def _child(tree, key):
    """The round-trip node under `key` (matched as text - the rt tree may type it differently)."""
    try:
        for candidate in tree:
            if str(candidate) == str(key):
                return tree[candidate]
    except Exception:  # noqa: BLE001
        pass
    return None


def _mark(node, part: str, key) -> tuple:
    """(line, column) of a mapping's key / value in the round-trip tree - (None, None) when unknown."""
    try:
        for candidate in node:                  # the rt tree may key it as another type (123 vs "123")
            if str(candidate) == str(key):
                return getattr(node.lc, part)(candidate)
    except Exception:  # noqa: BLE001
        pass
    return None, None


_DQ_ESCAPES = {"0": "\0", "a": "\a", "b": "\b", "t": "\t", "\t": "\t", "n": "\n", "v": "\v", "f": "\f",
               "r": "\r", "e": "\x1b", " ": " ", '"': '"', "/": "/", "\\": "\\", "N": "\x85", "_": "\xa0",
               "L": " ", "P": " "}
_DQ_HEX = {"x": 2, "u": 4, "U": 8}


def _quoted_chars(text: str, at: int, value: str):
    """The document offset of each character of a SINGLE-LINE quoted scalar's value (+ one for its
    end), the raw text decoded as YAML decodes it (`''` in single quotes; the backslash escapes in
    double quotes). None when that does not reproduce the value (a multi-line, folded scalar)."""
    quote, chars, decoded, i = text[at], [], [], at + 1
    while i < len(text):
        ch = text[i]
        if ch in "\r\n":
            return None
        if ch == quote:
            if quote == "'" and text.startswith("''", i):
                chars.append(i)
                decoded.append("'")
                i += 2
                continue
            break
        if quote == '"' and ch == "\\":
            code = text[i + 1:i + 2]
            if code in _DQ_ESCAPES:
                chars.append(i)
                decoded.append(_DQ_ESCAPES[code])
                i += 2
                continue
            width = _DQ_HEX.get(code)
            if width is None:
                return None
            try:
                decoded.append(chr(int(text[i + 2:i + 2 + width], 16)))
            except ValueError:
                return None
            chars.append(i)
            i += 2 + width
            continue
        chars.append(i)
        decoded.append(ch)
        i += 1
    if "".join(decoded) != value:
        return None
    return chars + [i]


_OTHER_BREAKS = re.compile("[\r\v\f\x1c\x1d\x1e\x85\u2028\u2029]")   # splitlines() breaks besides \n


def _scalar(text: str, starts: list, line: int, col: int, value: str) -> Scalar:
    """The content position of the scalar whose value starts at (line, col) - approximate when its value
    holds a line break besides `\\n` (the renderer splits on every one; the view's lines would not)."""
    scalar = _scalar_at(text, starts, line, col, value)
    if scalar.exact and _OTHER_BREAKS.search(value):
        scalar.exact = False
    return scalar


def _scalar_at(text: str, starts: list, line: int, col: int, value: str) -> Scalar:
    """The content position of the scalar whose value starts at (line, col) - a block (`|` exact, `>`
    folded), a quoted or a plain scalar."""
    at = starts[min(line, len(starts) - 1)] + col
    lead = text[at:at + 1]
    if lead in ("|", ">"):                      # a block: content from the next line, at its indent
        pieces = value.split("\n")
        first = min(line + 1, len(starts) - 1)
        indent = None
        if lead == "|":                         # read the indent off the DATA (an indentation
            for k, piece in enumerate(pieces):  # indicator `|2-` keeps extra spaces in the value)
                if piece.strip() and first + k < len(starts):
                    row = _row(text, starts, first + k)
                    if row.endswith(piece):
                        indent = len(row) - len(piece)
                    break
        if indent is None:                      # folded / unmatched: the first non-blank line's indent
            for index in range(first, len(starts)):
                row = _row(text, starts, index)
                if row.strip():
                    indent = len(row) - len(row.lstrip(" "))
                    break
        indent = indent or 0
        lines = [starts[min(first + k, len(starts) - 1)] + indent for k in range(max(1, len(pieces)))]
        return Scalar(lines, exact=lead == "|")
    if lead in ("'", '"'):
        chars = _quoted_chars(text, at, value)
        return Scalar([at + 1], exact=chars is not None, chars=chars, value=value)
    return Scalar([at], exact=text.startswith(value, at))


# --- highlighting ----------------------------------------------------------------------------------- #
def spans(doc: Doc, language: str | None = None) -> list:
    """(tag, start, end) over the document, in layering order: YAML for the structure (not inside a
    text template's body), then the system's target `language` under each text template (a langs.json
    key - its `template_language`; None = no language layer), then the template constructs on top
    (the view raises the tp_/tx_ tags)."""
    bodies = [(entry.body.starts[0], entry.body.end(entry.text)) for entry in doc.entries.values()
              if entry.kind == "text" and entry.body is not None]
    out = [(tag, start, end) for tag, start, end in highlight.spans("yaml", doc.text)
           if not any(low <= start < high for low, high in bodies)]
    for entry in doc.entries.values():
        if entry.kind == "text" and entry.body is not None and entry.body.exact:
            if language:
                for tag, start, end in highlight.spans(language, entry.text):
                    out.append((tag, entry.body.at(start, entry.text), entry.body.at(end, entry.text)))
            for number, line in enumerate(entry.text.split("\n")):
                for tag, start, end in _line_spans(line):
                    out.append((tag, entry.body.offset(number, start), entry.body.offset(number, end)))
        elif entry.kind == "row":
            for key, scalar in entry.values.items():
                if not scalar.exact:
                    continue                                # a folded value: no misplaced colours
                value = entry.value_text[key]
                for tag, start, end in _value_spans(value):
                    out.append((tag, scalar.at(start, value), scalar.at(end, value)))
    return out


def _line_spans(line: str) -> list:
    """The template layer of ONE text-template line (its roles from tempemplator.outline)."""
    out = []
    for role, start, end in tempemplator.outline(line):
        if role in _ROLE_TAGS:
            out.append((_ROLE_TAGS[role], start, end))
        elif role == "predicate":
            out.extend(_expr_spans(line[start:end], start))
        elif role in ("fragment", "text"):
            out.extend(_value_spans(line[start:end], start))
        elif role == "body":
            out.extend((tag, start + s, start + e) for tag, s, e in _line_spans(line[start:end]))
    return out


def _value_spans(text: str, base: int = 0) -> list:
    """Holes (braces + expression tokens + a format spec) and doubled literal braces in text."""
    out = []
    for kind, start, end in tempemplator.brace_runs(text):
        if kind == "brace":
            out.append(("tp_literal", base + start, base + end))
        elif kind == "hole":
            out += [("tp_hole", base + start, base + start + 1), ("tp_hole", base + end - 1, base + end)]
            body = text[start + 1:end - 1]
            expression, spec = tempemplator.hole_parts(body)
            out.extend(_expr_spans(expression, base + start + 1))
            if spec is not None:
                out.append(("tp_spec", base + end - 1 - len(spec), base + end - 1))
    return out


def _expr_spans(text: str, base: int) -> list:
    return [(f"tx_{kind}", base + start, base + end) for kind, start, end in expr.tokens(text)
            if f"tx_{kind}" in TAG_COLORS]


# --- problems ------------------------------------------------------------------------------------------ #
def place(doc: Doc, problems) -> list:
    """The engine's lint problems (tempemplator.Problem) -> [Placed]: a text template's (line, columns)
    through its block's content lines, a row value's character offsets through its scalar, a whole
    entry at its name, a RULE problem (template None) without a position. The YAML error first."""
    out = []
    if doc.error is not None:
        start = doc.error[0]
        out.append(Placed(start, min(start + 1, len(doc.text)) if doc.text else start, doc.error[1],
                          "error", "templates.yaml"))
    for problem in problems:
        entry = doc.entries.get(str(problem.template)) if problem.template is not None else None
        if entry is None:
            label = "rule" if problem.template is None else str(problem.template)
            out.append(Placed(None, None, problem.message, problem.severity, label))
            continue
        end = max(problem.end, problem.start + 1)
        where = problem.where
        if isinstance(where, int) and entry.body is not None:
            if entry.body.exact:
                start = entry.body.offset(where - 1, problem.start)
                stop = entry.body.offset(where - 1, end)
                label = f"{entry.name} line {where}"
            else:                                           # a folded body: its lines are not the document's
                (start, stop), label = entry.body.first_line(doc.text), f"{entry.name} line {where} (approximate)"
        elif isinstance(where, tuple) and (where[0], str(where[1])) in entry.values:
            key = (where[0], str(where[1]))
            value, scalar = entry.value_text[key], entry.values[key]
            if scalar.exact:
                start, stop = scalar.at(problem.start, value), scalar.at(end, value)
                label = f"{entry.name} entry {where[0]} {where[1]}"
            else:                                           # a folded value: approximate - its first line
                (start, stop), label = scalar.first_line(doc.text), \
                    f"{entry.name} entry {where[0]} {where[1]} (approximate)"
        else:
            (start, stop), label = entry.key, entry.name
        out.append(Placed(start, stop, problem.message, problem.severity, label))
    return out


# --- completions ------------------------------------------------------------------------------------- #
_DIRECTIVE_STEM = re.compile(r"^\s*(@\w*)$")
_USE_STEM = re.compile(r"^\s*@use\s+(\S*)$", re.IGNORECASE)
_TABLE_STEM = re.compile(r"^\s*@for\s+\$\w+\s+in\s+([A-Za-z_]\w*)?$", re.IGNORECASE)


def completions(doc: Doc, at: int, context: Context | None = None) -> tuple:
    """(stem start, [candidates]) for the cursor at document offset `at` - (at, []) when nothing fits
    (the cursor is in the YAML structure, or no candidate matches the stem)."""
    context = context or Context()
    found = _locate(doc, at)
    if found is None:
        return at, []
    entry, number, line, column, to_doc = found
    before = line[:column]
    if entry.kind == "text":
        stem = _DIRECTIVE_STEM.match(before)
        if stem:
            word = stem.group(1).lower()
            return at - len(stem.group(1)), [d for d in _DIRECTIVES if d.startswith(word) and d != word]
        stem = _USE_STEM.match(before)
        if stem:
            names = [n for n, e in doc.entries.items() if e.kind == "text" and n != entry.name]
            return at - len(stem.group(1)), _prefixed(stem.group(1), names)
        stem = _TABLE_STEM.match(before)
        if stem:
            word = stem.group(1) or ""
            return at - len(word), _prefixed(word, sorted(context.tables or ()))
    where_table = _where_table(entry, line, column)
    if where_table is None and not _in_expression(entry, line, column):
        return at, []
    word, start = _word_before(line, column)
    if not word:
        return at, []
    row_table = where_table if where_table is not None else _data_table(line[:start])
    if row_table is not None and word.startswith("$"):      # a `where` / data function's predicate sees
        columns = (context.tables or {}).get(row_table) or ()   # that table's ROW columns - only
        return to_doc(start), [f"${c}" for c in _prefixed(word[1:], list(columns))]
    loops = _loops_at(entry, number, line, column, context)
    in_reach = context.reach is None or entry.name in context.reach
    return to_doc(start), _expression_candidates(word, loops, context, in_reach)


def _locate(doc: Doc, at: int):
    """The template text around `at`: (entry, line number or value key, the line's text, the column,
    a column -> document offset map) - None outside every template. A quoted row value maps through
    its decoded characters (an escape is two document characters for one value character)."""
    for entry in doc.entries.values():
        if entry.kind == "text" and entry.body is not None and entry.body.chars is not None:
            chars = entry.body.chars                  # a quoted template: the cursor maps through its chars
            if chars[0] <= at <= chars[-1]:
                index = max(i for i, offset in enumerate(chars) if offset <= at)
                number = entry.text.count("\n", 0, index)
                begin = entry.text.rfind("\n", 0, index) + 1
                return entry, number, entry.text.split("\n")[number], index - begin, \
                    (lambda i, c=chars, b=begin: c[max(0, min(b + i, len(c) - 1))])
        elif entry.kind == "text" and entry.body is not None:
            for number, line in enumerate(entry.text.split("\n")):
                start = entry.body.offset(number, 0)
                if start <= at <= start + len(line):
                    return entry, number, line, at - start, (lambda i, s=start: s + i)
        elif entry.kind == "row":
            for key, scalar in entry.values.items():
                value = entry.value_text[key]
                if scalar.chars is not None:          # a quoted value: the cursor maps through its chars
                    if scalar.chars[0] <= at <= scalar.chars[-1]:
                        index = max(i for i, offset in enumerate(scalar.chars) if offset <= at)
                        return entry, key, value, index, (lambda i, c=scalar.chars: c[max(0, min(i, len(c) - 1))])
                    continue
                for index, line in enumerate(value.split("\n")):
                    start = scalar.offset(index, 0)
                    if start <= at <= start + len(line):
                        return entry, key, line, at - start, (lambda i, s=start: s + i)
    return None


def _where_table(entry: Entry, line: str, column: int):
    """The loop TABLE whose `where` predicate holds the cursor (None = not in a `where`)."""
    if entry.kind != "text":
        return None
    parts = _outline_all(line)
    for index, (role, start, end) in enumerate(parts):
        if role == "predicate" and start <= column <= end and index and parts[index - 1][0] == "keyword" \
                and line[parts[index - 1][1]:parts[index - 1][2]].lower() == "where":
            tables = [line[s:e] for r, s, e in parts[:index] if r == "table"]
            return tables[-1] if tables else None
    return None


_ROW_FUNCTIONS = ("count", "where", "first")               # a data function whose 2nd argument is a predicate


def _data_table(before: str):
    """The table whose ROWS the text at the end of `before` is evaluated against - the innermost
    enclosing `count(<table>, ...` / `where(` / `first(` past its first argument - or None. A quoted
    string or a /regex/ is opaque (its parentheses and commas are not the call's)."""
    depth, commas, i, quote = 0, 0, len(before) - 1, ""
    while i >= 0:
        ch = before[i]
        if quote:
            if ch == quote:
                quote = ""
        elif ch in "\"'/":
            quote = ch
        elif ch == ")":
            depth += 1
        elif ch == "," and depth == 0:
            commas += 1
        elif ch == "(":
            if depth:
                depth -= 1
            else:
                name = re.search(r"(\w+)\s*$", before[:i])
                if name and name.group(1) in _ROW_FUNCTIONS and commas:
                    table = before[i + 1:].split(",", 1)[0].strip().strip('"')
                    return table or None
                commas = 0                                  # a plain call: keep looking outward
        i -= 1
    return None


def _in_expression(entry: Entry, line: str, column: int) -> bool:
    """The cursor is inside an expression: an open or closed hole, or an @if predicate."""
    runs = tempemplator.brace_runs(line[:column])
    if runs and runs[-1][0] == "lone" and line[runs[-1][1]] == "{":
        return True                                             # typing inside a hole not yet closed
    if len(runs) >= 2 and runs[-2][0] == "lone" and line[runs[-2][1]] == "{" and runs[-1][0] == "text":
        return True
    if any(kind == "hole" and start < column < end for kind, start, end in tempemplator.brace_runs(line)):
        return True
    if entry.kind == "text":
        return any(role == "predicate" and start <= column <= end for role, start, end in _outline_all(line))
    return False


def _outline_all(line: str) -> list:
    """outline + the inline body's own parts (offset into the line)."""
    parts = []
    for role, start, end in tempemplator.outline(line):
        parts.append((role, start, end))
        if role == "body":
            parts.extend((r, start + s, start + e) for r, s, e in tempemplator.outline(line[start:end]))
    return parts


def _word_before(line: str, column: int) -> tuple:
    """(word, start) - the $field / identifier fragment ending at `column` (('', column) when none)."""
    start = column
    while start > 0 and (line[start - 1].isalnum() or line[start - 1] in "_.$"):
        start -= 1
    word = line[start:column]
    if word.startswith("$") or (word and (word[0].isalpha() or word[0] == "_")):
        return word, start
    return "", column


def _loops_at(entry: Entry, number, line: str, column: int, context: Context) -> dict:
    """{loop var: its table's columns (None = a range / unknown)} active at the cursor - the enclosing
    block @for loops of this text template + an inline @for on the cursor's own line."""
    loops = {}
    if entry.kind != "text":
        return loops
    stack = []
    for current in entry.text.split("\n")[:number]:
        parts = dict((role, (s, e)) for role, s, e in tempemplator.outline(current))
        word = current.strip().split(None, 1)[0].lower() if current.strip().startswith("@") else ""
        if word == "@for" and "body" not in parts:
            stack.append(_loop_of(current, parts, context))
        elif word == "@if":
            stack.append(None)
        elif word == "@end" and stack:
            stack.pop()
    parts = dict((role, (s, e)) for role, s, e in tempemplator.outline(line))
    if "body" in parts and column >= parts["body"][0]:
        stack.append(_loop_of(line, parts, context))
    for loop in stack:
        if loop is not None:
            loops[loop[0]] = loop[1]
    return loops


def _loop_of(line: str, parts: dict, context: Context):
    if "var" not in parts:
        return None
    var = line[parts["var"][0] + 1:parts["var"][1]]
    table = line[slice(*parts["table"])] if "table" in parts else None
    columns = (context.tables or {}).get(table) if table else None
    return var, (tuple(columns) if columns is not None else None)


def _expression_candidates(word: str, loops: dict, context: Context, in_reach: bool) -> list:
    if word.startswith("$"):
        head, dot, rest = word[1:].partition(".")
        if dot:
            if head in loops:
                pool = loops[head] or ()
            elif head == "_params":
                node = context.params
                parts = rest.split(".")
                for key in parts[:-1]:
                    node = node.get(key) if isinstance(node, dict) else None
                pool = sorted(node) if isinstance(node, dict) else ()
                head = ".".join(["_params"] + parts[:-1])
                rest = parts[-1]
            elif head == "_rule":
                pool = ("name", "hook")
            else:
                pool = ()
            return [f"${head}.{c}" for c in _prefixed(rest, list(pool))]
        names = set(loops) | {"_params", "_rule"} | (set(context.fields or ()) if in_reach else set())
        names.discard("_db")
        return [f"${n}" for n in _prefixed(head, sorted(names))]
    pool = list(expr.function_names()) + ["and", "or", "not", "in"] + sorted(context.tables or ())
    return [w for w in _prefixed(word, pool) if w.lower() != word.lower()]


def _prefixed(stem: str, pool) -> list:
    stem = stem.lower()
    return [item for item in pool if str(item).lower().startswith(stem) and str(item).lower() != stem]


def reach(templates: dict, start: str) -> frozenset:
    """The templates a render of `start` splices (itself included) - through @use, transitively."""
    seen, todo = set(), [start]
    while todo:
        name = todo.pop()
        if name in seen or name not in templates:
            continue
        seen.add(name)
        if isinstance(templates[name], str):
            todo += [ref for _line, _span, ref in tempemplator.use_refs(templates[name])]
    return frozenset(str(name) for name in seen)


# --- the live session (the view's state, Tk-free) ---------------------------------------------------- #
def is_templates_file(path: str) -> bool:
    """A chain-reaction templates file - `chain_reactions/templates.yaml` in any tier - opens in the
    template mode."""
    parts = os.path.normcase(os.path.abspath(path)).split(os.sep)
    return parts[-1:] == ["templates.yaml"] and parts[-2:-1] == ["chain_reactions"]


_VIEW_CACHE = 8                                  # views kept per session (the templates change as one types)


class Session:
    """The builder's live context over the ACTIVE config - the compiled rules (reactions.csv), the
    system's `reaction_hooks` / `reaction_legs`, the project params - and the Database each rule's fire
    GETS, the run-plan modelled:

      1. the hook's declared loader - the system's own input for it, rebuilt IN MEMORY through the
         run-plan's own gate (Siemens after_300: staging itself, the treatments registry applied,
         nothing saved) - NOT the Database/ folder, which later phases re-save. A run that halts
         before the hook raises engine.WouldNotFire: the builder then says the hook never fires;
      2. a DATABASE-LESS hook fired earlier WITH business (engine.has_business) is settled into the
         next database: a DRY fire of it (the real `fire` with write=False - its file rules write
         nothing) and its Deferred applied exactly as `settle` applies it (engine.settle_view - the
         record attached, the hook's audit rows replaced, its findings recorded - nothing saved);
      3. the in-hook CASCADE: the rows the hook's earlier add_rows rules spawn (engine.cascade);
      4. the OTHER legs that fire the hook (System.reaction_legs - Siemens: the 310 Stage-I/O-List
         leg) - each rule is linted against them too; what only a leg rejects is reported as such.

    Building a Database can take a while on a big project - the view constructs the Session (reading
    the config files, no build) and then does the WORK (reload, base / view, check, row_count,
    preview_text, context) on ONE worker thread (template_mode.py); its Tk thread only reads plain
    state (rule_labels, rule, loaded, language, notes). A build a reload overtakes is discarded
    (`generation`). `check` = the lint placed on the document; `preview_text` = one fire for one
    row, as text, with the notes that matter."""

    def __init__(self, path: str | None = None, *, rows=None, hooks=None, params=None, legs=None):
        """`rows` / `hooks` / `params` / `legs` replace what `reload` reads from the active config and
        system (a test's seam; the view passes only the document's path). Given `hooks` replace the
        system's hook declaration as a whole - its legs too, unless `legs` are given."""
        self.path = path
        if hooks is not None and legs is None:
            legs = {}
        self._given = {"rows": rows, "hooks": hooks, "params": params, "legs": legs}
        self._lock = threading.Lock()
        self.generation = 0
        self.reload()

    def reload(self) -> None:
        from pipeline5 import config
        from pipeline5.config.resolver import find
        from pipeline5.phases.chain_reactions import engine
        from pipeline5.systems import catalog
        notes = []                                        # what could not load - shown, never raised
        rows_ok = True
        try:
            rows = config.load_reactions() if self._given["rows"] is None else list(self._given["rows"])
        except Exception as error:  # noqa: BLE001 - the engine reports rx_rules_unreadable; so do we
            rows, rows_ok = [], False
            notes.append(f"reactions.csv does not load: {error}")
        rules, findings = engine.compile_rules(rows)
        notes += [f"{f.type}: {f.detail}" for f in findings]
        active = config.active_system()
        system = catalog.by_id(active[0]) if active else None
        given_hooks, given_legs = self._given["hooks"], self._given["legs"]
        hooks = dict((getattr(system, "reaction_hooks", None) or {}) if given_hooks is None else given_hooks)
        legs = {hook: dict(named) for hook, named in ((getattr(system, "reaction_legs", None) or {})
                                                      if given_legs is None else given_legs).items()}
        if not hooks:
            notes.append("the active system declares no reaction hooks (System.reaction_hooks) - "
                         "nothing to preview against")
        params_problem = None
        try:
            params = config.load_params() if self._given["params"] is None else self._given["params"]
        except Exception as error:  # noqa: BLE001 - the fire blocks the hook's rules: rx_params_unreadable
            params, params_problem = {}, str(error)
            notes.append(f"project params do not load: {error}")
        templates_file = find("chain_reactions/templates.yaml")
        with self._lock:                                  # published AT ONCE: the new generation and its fresh
            self.generation += 1                          # caches - a build or a view started before is discarded
            self.notes, self.rows_ok, self.rows, self.rules = notes, rows_ok, rows, rules
            self.system, self.hooks, self.legs = system, hooks, legs
            self.language = getattr(system, "template_language", "") or None
            self.params, self.params_problem, self.active = params, params_problem, templates_file
            self._bases, self._halts, self._views = {}, {}, {}

    # --- the Database a fire gets ---------------------------------------------------------------- #
    def _loader(self, hook: str, leg):
        return self.hooks.get(hook) if leg is None else self.legs.get(hook, {}).get(leg)

    def loaded(self, hook: str) -> bool:
        """Whether every Database `hook` fires over (its legs included) is built - a database-less or
        undeclared one always is."""
        with self._lock:
            return all(self._loader(hook, leg) is None or (hook, leg) in self._bases
                       for leg in (None, *self.legs.get(hook, {})))

    def base(self, hook: str, leg=None):
        """The Database `hook`'s fire gets from the run-plan's own input (1 above) on the main leg or
        `leg` - None when database-less, when the run stops before the hook, or when it cannot be built
        (the run's own staging would fail there: a halt too - noted). Built once per session; slow for a
        big project."""
        from pipeline5.phases.chain_reactions import engine
        key = (hook, leg)
        with self._lock:
            if key in self._bases:
                return self._bases[key]
            generation = self.generation
        loader, database, halt, note = self._loader(hook, leg), None, None, None
        if loader is not None:
            try:
                database = loader(self.system)
            except engine.WouldNotFire as error:
                halt = str(error)
            except Exception as error:  # noqa: BLE001 - e.g. a source document that will not open
                note = f"the {hook} database{f' ({leg})' if leg else ''} cannot be built: {error}"
                halt = f"its Database cannot be built ({error}) - the run stops there"   # its staging fails too
        with self._lock:
            if generation != self.generation:              # reloaded meanwhile: this build is stale
                return database
            if halt:
                self._halts[key] = halt
            if note:
                self.notes.append(note)
            self._bases.setdefault(key, database)
            return self._bases[key]

    def halt(self, hook: str, leg=None):
        """Why the run stops before `hook` fires on that leg - a halt, a downgraded raw FAIL, a Database
        that cannot be built (None = it fires)."""
        self.base(hook, leg)
        with self._lock:
            return self._halts.get((hook, leg))

    def _pending(self, hook: str) -> list:
        """The database-less hooks fired before `hook` (since the previous database) WITH business -
        each is settled into `hook`'s database (the run-plan's duty)."""
        from pipeline5.phases.chain_reactions import engine
        order, pending = list(self.hooks), []
        for name in order:
            if name == hook:
                return pending
            if self.hooks[name] is None:
                if not self.rows_ok or engine.has_business(name, self.rows, tuple(order)):
                    pending.append(name)
            else:
                pending = []
        return []

    def view(self, rule, templates: dict, leg=None) -> tuple:
        """(the Database `rule` sees at its hook on that leg - the base, the settled earlier hooks (2),
        the earlier rules' in-hook spawns (3) - and its `_db` layer); cached per (hook, leg, the
        templates those earlier rules render)."""
        from pipeline5.phases.chain_reactions import engine
        with self._lock:
            generation = self.generation
        base = self.base(rule.fire_when, leg)
        notes = []
        pending = self._pending(rule.fire_when) if base is not None else []
        index = self.rules.index(rule)
        earlier = [r for r in self.rules[:index] if r.fire_when == rule.fire_when and r.action == "add_rows"]
        drivers = [r for r in self.rules if r.fire_when in pending] + earlier
        used = sorted({name for r in drivers for name in reach(templates, r.template)})
        key = (rule.fire_when, leg, tuple(pending), tuple(r.name for r in earlier),
               tuple((name, repr(templates.get(name))) for name in used))
        cached = self._views.get(key)                     # (one read: a reload may swap the cache)
        if cached is None:
            database = base
            if database is not None and pending:
                database = engine.copy_database(database)
                for hook in pending:                          # a DRY fire: its file rules write nothing
                    deferred, _findings = engine.fire(
                        hook, None, rules=self.rows if self.rows_ok else None, templates=templates,
                        params=None if self.params_problem else self.params, hooks=tuple(self.hooks),
                        write=False)
                    if deferred is not None:
                        notes += engine.settle_view(database, deferred)
            if not self.params_problem:                   # (unreadable params block every rule: no spawns)
                database, _problems = engine.cascade(self.rules, rule, database, templates=templates,
                                                     params=self.params)
            view = (database, engine.db_layer(database))
            with self._lock:                              # the check AND the write: a reload cannot land between
                if generation != self.generation:         # reloaded meanwhile: over a stale build - never cached
                    return view
                self.notes += [n for n in notes if n not in self.notes]
                while len(self._views) >= _VIEW_CACHE:
                    self._views.pop(next(iter(self._views)))
                self._views[key] = view
            return view
        return cached

    # --- the view's questions -------------------------------------------------------------------------- #
    def rule_labels(self) -> list:
        return ["(no rule - the syntax checks only)"] + [
            f"{r.name}  ·  {r.fire_when}  ·  {r.action} -> {r.target}" for r in self.rules]

    def rule(self, index: int):
        """The rule at `index` of `rule_labels()` (0 = no rule)."""
        return self.rules[index - 1] if 1 <= index <= len(self.rules) else None

    def ready(self, rule) -> bool:
        return rule is None or self.loaded(rule.fire_when)

    def row_count(self, rule, templates: dict) -> int:
        """How many source rows the rule's fire matches over (0: source-less, or no such table there)."""
        if rule is None or not rule.source_table:
            return 0
        database, _layer = self.view(rule, templates)
        if database is None or rule.source_table not in database:
            return 0
        return len(database[rule.source_table])

    def context(self, rule, templates: dict) -> Context:
        """The completion context for `rule` (None: the document alone)."""
        if rule is None:
            return Context(params=self.params)
        leg = None
        if self.halt(rule.fire_when):                     # the main leg stops: a leg that fires names it
            leg = next((name for name in self.legs.get(rule.fire_when, {}) if not self.halt(rule.fire_when, name)),
                       None)
        database, _layer = self.view(rule, templates, leg)
        tables = {} if database is None else {n: database[n].effective_columns() for n in database.names()}
        fields = None
        if not rule.source_table or rule.source_table in tables:
            fields = frozenset({"_params", "_rule", "_db"} | set(tables.get(rule.source_table, ())))
        return Context(fields=fields, tables=tables, params=self.params,
                       reach=reach(templates, rule.template) if rule.action == "file" else frozenset({rule.template}))

    def check(self, doc: Doc, rule) -> list:
        """engine.lint on the document - in the rule's context when one is chosen, on every leg that
        fires its hook (what only another leg rejects says so). A leg the run halts on says THAT instead -
        no checks of a fire that never happens - and the other legs are checked all the same."""
        from pipeline5.phases.chain_reactions import engine
        if doc.error is not None:
            return place(doc, [])
        hooks = tuple(self.hooks) or None
        if rule is None:
            return place(doc, engine.lint(doc.templates, None, None, hooks))
        halt = self.halt(rule.fire_when)
        if halt:                                          # the main leg never fires: nothing it would report
            placed = place(doc, engine.lint(doc.templates, None, None, hooks)) + [
                Placed(None, None, f"the run stops before {rule.fire_when} fires - {halt}", "warning", "rule")]
        else:
            placed = place(doc, engine.lint(doc.templates, rule, self.view(rule, doc.templates)[0], hooks))
        seen = {(p.start, p.end, p.message) for p in placed}
        fires = not halt
        for leg in self.legs.get(rule.fire_when, {}):
            leg_halt = self.halt(rule.fire_when, leg)
            if leg_halt:
                placed.append(Placed(None, None, f"on the {leg} leg: {leg_halt}", "warning", "rule"))
                continue
            fires = True
            for p in place(doc, engine.lint(doc.templates, rule, self.view(rule, doc.templates, leg)[0], hooks)):
                if (p.start, p.end, p.message) not in seen:
                    seen.add((p.start, p.end, p.message))
                    placed.append(Placed(p.start, p.end, f"on the {leg} leg: {p.message}", p.severity, p.label))
        if fires and self.params_problem:                 # a fire blocks every rule of the hook
            placed.append(Placed(None, None, f"rule {rule.name!r}: rx_params_unreadable - the project params do "
                                 f"not load, a fire blocks every rule of the hook: {self.params_problem}",
                                 "error", "rule"))
        return placed

    def document_note(self) -> str:
        """A note when this document is NOT the templates.yaml a fire uses (its lint and preview are
        about this document all the same)."""
        if not self.path:
            return ""
        if not self.active:
            return "note: no chain_reactions/templates.yaml is active - a fire finds no templates"
        if os.path.normcase(os.path.abspath(self.path)) != os.path.normcase(os.path.abspath(self.active)):
            return (f"note: a fire uses {self.active}, NOT this document - the preview renders this "
                    "document's templates")
        return ""

    def preview_text(self, doc: Doc, rule, row: int) -> str:
        """What ONE fire of `rule` would do for source row `row` (engine.preview), as text."""
        from pipeline5.phases.chain_reactions import engine
        if rule is None:
            return "Choose a rule to preview what a fire would do for one of its rows."
        if doc.error is not None:
            return "templates.yaml does not load - fix it to preview."
        lines = [note for note in (self.document_note(),) if note]
        halt = self.halt(rule.fire_when)
        if halt:
            firing = [leg for leg in self.legs.get(rule.fire_when, {}) if not self.halt(rule.fire_when, leg)]
            return "\n".join(lines + [f"the run stops before {rule.fire_when} fires - {halt}",
                                      "(no fire, so nothing to preview)"] +
                             [f"note: the {leg} leg fires {rule.fire_when} all the same, over its own Database - "
                              "its problems are in the problems list ('on the ... leg')" for leg in firing])
        if self.params_problem:
            return "\n".join(lines + [f"rx_params_unreadable: the project params do not load - a fire blocks "
                                      f"every rule of {rule.fire_when}: {self.params_problem}"])
        database, layer = self.view(rule, doc.templates)
        shown = engine.preview(rule, row, templates=doc.templates, params=self.params, database=database,
                               layer=layer, hooks=tuple(self.hooks) or None)
        if shown.note:
            lines.append(shown.note)
        if shown.matched is False:
            lines.append("(this row does NOT match the rule's condition - a fire skips it; rendered anyway:)")
        if shown.problem is not None:
            lines.append(f"{shown.problem[0]}: {shown.problem[1]}")
        elif rule.action == "file" and not shown.note:
            lines += [f"APPEND to {shown.path}:", shown.text]
        if shown.rows:
            lines.append(f"SPAWN into {rule.target}:")
            lines += ["  " + ", ".join(f"{k}={v!r}" for k, v in row_values.items()) for row_values in shown.rows]
            if database is not None and rule.target in database and self._restaged(rule):
                lines.append(f"note: later phases re-stage {rule.target} from the source documents - these rows "
                             "reach the saved Database, not generation (C-024's known boundary)")
        for leg in self.legs.get(rule.fire_when, {}):
            lines.append(f"note: the {leg} leg also fires {rule.fire_when}, over its own Database - what only "
                         "it rejects is in the problems list ('on the ... leg')")
        return "\n".join(lines)

    def _restaged(self, rule) -> bool:
        """Whether the rule's target is a table the hook's declared loader builds (a staged table that
        later phases rebuild from the documents)."""
        with self._lock:
            base = self._bases.get((rule.fire_when, None))
        return base is not None and rule.target in base
