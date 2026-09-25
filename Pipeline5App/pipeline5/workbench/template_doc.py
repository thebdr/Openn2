"""The templates.yaml EDITING MODEL behind the Files tab's template mode (P-012) - Tk-free and tested;
src://pipeline5/workbench/files_panel.py is the view over it.

A `chain_reactions/templates.yaml` is ONE YAML mapping of named templates: a TEXT template (a block
scalar - the `file` action) or a ROW template (a list of {field: template} maps - `add_rows`). This
module reads the document exactly as the engine does (the same loader: a YAML error here is the
engine's rx_templates_unreadable) and remembers WHERE every template line and row value sits, so the
builder can:

    parse(text)                  -> Doc: the engine's view (`templates`) + every scalar's position
    spans(doc)                   two-layer highlighting - the target language (SCL) UNDER the template
                                 constructs (@directives, @use references, {holes} with their
                                 expression tokens, {{ }} literal braces); YAML for the structure
    place(doc, problems)         the engine's lint problems (engine.lint) -> document offsets + labels
    completions(doc, at, ctx)    what fits at the cursor: the rule's columns, loop vars and _params
                                 keys after `$`, a loop row's columns after `$var.`, templates after
                                 `@use`, tables in `@for ... in`, directives after `@`, functions

The grammar is never re-derived here: lines are read through the renderer's own views
(tempemplator.outline / brace_runs / hole_parts - src://pipeline5/language/tempemplator.py).
"""
from __future__ import annotations

import re
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
    """Where one YAML scalar's CONTENT sits: the document offset of each content line's first column.
    `exact` False = a folded block / a quoted scalar with escapes (positions approximate)."""
    starts: list
    exact: bool = True

    def offset(self, line: int, column: int) -> int:
        """(0-based content line, column) -> the document offset."""
        return self.starts[max(0, min(line, len(self.starts) - 1))] + max(0, column)

    def at(self, index: int, value: str) -> int:
        """A character offset into the scalar's VALUE -> the document offset."""
        line = value.count("\n", 0, index)
        return self.offset(line, index - (value.rfind("\n", 0, index) + 1))


@dataclass
class Entry:
    name: str
    kind: str                                   # "text" | "row" | "other"
    key: tuple                                  # (start, end) of the name
    body: Scalar | None = None                  # text: the block's content lines
    values: dict = field(default_factory=dict)  # row: {(entry number, field): Scalar}


@dataclass
class Doc:
    text: str
    templates: dict                             # the engine's view ({} when the YAML does not load)
    entries: dict                               # name -> Entry
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


# --- parse ---------------------------------------------------------------------------------------- #
def _line_starts(text: str) -> list:
    starts = [0]
    for match in re.finditer("\n", text):
        starts.append(match.end())
    return starts


def parse(text: str) -> Doc:
    """The document as the engine loads it (the safe loader - config.params._read_yaml) + WHERE each
    template sits (a round-trip parse's line/column marks)."""
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
    for name, body in templates.items():
        name = str(name)
        key_line, key_col = _mark(tree, "key", name)
        key = (offset(key_line, key_col), offset(key_line, key_col) + len(name)) if key_line is not None else (0, 0)
        if isinstance(body, str):
            line, col = _mark(tree, "value", name)
            scalar = _scalar(text, starts, line, col, body) if line is not None else None
            entries[name] = Entry(name, "text", key, body=scalar)
        elif isinstance(body, list):
            values = {}
            items = tree.get(name) if tree is not None and hasattr(tree, "get") else None
            for number, spec in enumerate(body, start=1):
                item = items[number - 1] if items is not None and number - 1 < len(items) else None
                if not isinstance(spec, dict) or not hasattr(item, "lc"):
                    continue
                for column, value in spec.items():
                    if isinstance(value, str):
                        line, col = _mark(item, "value", column)
                        if line is not None:
                            values[(number, str(column))] = _scalar(text, starts, line, col, value)
            entries[name] = Entry(name, "row", key, values=values)
        else:
            entries[name] = Entry(name, "other", key)
    return Doc(text, templates, entries)


def _mark(node, part: str, key) -> tuple:
    """(line, column) of a mapping's key / value in the round-trip tree - (None, None) when unknown."""
    try:
        for candidate in node:                  # the rt tree may key it as another type (123 vs "123")
            if str(candidate) == str(key):
                return getattr(node.lc, part)(candidate)
    except Exception:  # noqa: BLE001
        pass
    return None, None


def _scalar(text: str, starts: list, line: int, col: int, value: str) -> Scalar:
    """The content position of the scalar whose value starts at (line, col) - a block (`|` exact,
    `>` folded), a quoted or a plain scalar."""
    at = starts[min(line, len(starts) - 1)] + col
    lead = text[at:at + 1]
    if lead in ("|", ">"):                      # a block: content from the next line, at its indent
        count = max(1, len(value.split("\n")))
        first = min(line + 1, len(starts) - 1)
        indent = None
        for index in range(first, len(starts)):
            row = text[starts[index]:starts[index + 1] if index + 1 < len(starts) else len(text)].rstrip("\n")
            if row.strip():
                indent = len(row) - len(row.lstrip(" "))
                break
        indent = indent or 0
        lines = [starts[min(first + k, len(starts) - 1)] + indent for k in range(count)]
        return Scalar(lines, exact=lead == "|")
    if lead in ("'", '"'):                      # quoted: exact while the raw text IS the value
        raw = text[at + 1:at + 1 + len(value)]
        return Scalar([at + 1], exact=raw == value and "\n" not in value)
    return Scalar([at], exact="\n" not in value)


# --- highlighting ----------------------------------------------------------------------------------- #
def spans(doc: Doc) -> list:
    """(tag, start, end) over the document, in layering order: YAML for the structure (not inside a
    text template's body), then the target language (SCL) under each text template, then the
    template constructs on top (the view raises the tp_/tx_ tags)."""
    bodies = []
    out = []
    for entry in doc.entries.values():
        if entry.kind == "text" and entry.body is not None:
            body = doc.templates.get(entry.name, "")
            bodies.append((entry.body.starts[0], entry.body.at(len(body), body)))
    for tag, start, end in highlight.spans("yaml", doc.text):
        if not any(low <= start < high for low, high in bodies):
            out.append((tag, start, end))
    for entry in doc.entries.values():
        if entry.kind == "text" and entry.body is not None:
            body = doc.templates.get(entry.name, "")
            for tag, start, end in highlight.spans("scl", body):
                out.append((tag, entry.body.at(start, body), entry.body.at(end, body)))
            for number, line in enumerate(body.split("\n")):
                for tag, start, end in _line_spans(line):
                    out.append((tag, entry.body.offset(number, start), entry.body.offset(number, end)))
        elif entry.kind == "row":
            rows = doc.templates.get(entry.name) or []
            for (number, column), scalar in entry.values.items():
                value = rows[number - 1][column]
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
        entry = doc.entries.get(problem.template) if problem.template is not None else None
        if entry is None:
            label = "rule" if problem.template is None else str(problem.template)
            out.append(Placed(None, None, problem.message, problem.severity, label))
            continue
        end = max(problem.end, problem.start + 1)
        if isinstance(problem.where, int) and entry.body is not None:
            start = entry.body.offset(problem.where - 1, problem.start)
            stop = entry.body.offset(problem.where - 1, end)
            label = f"{entry.name} line {problem.where}"
        elif isinstance(problem.where, tuple) and problem.where in entry.values:
            value = doc.templates[entry.name][problem.where[0] - 1][problem.where[1]]
            scalar = entry.values[problem.where]
            start, stop = scalar.at(problem.start, value), scalar.at(end, value)
            label = f"{entry.name} entry {problem.where[0]} {problem.where[1]}"
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
    entry, number, line, column, line_start = found
    before = line[:column]
    if entry.kind == "text":
        stem = _DIRECTIVE_STEM.match(before)
        if stem:
            word = stem.group(1).lower()
            return at - len(stem.group(1)), [d for d in _DIRECTIVES if d.startswith(word) and d != word]
        stem = _USE_STEM.match(before)
        if stem:
            names = [n for n, body in doc.templates.items() if isinstance(body, str) and n != entry.name]
            return at - len(stem.group(1)), _prefixed(stem.group(1), names)
        stem = _TABLE_STEM.match(before)
        if stem:
            word = stem.group(1) or ""
            return at - len(word), _prefixed(word, sorted(context.tables or ()))
    if not _in_expression(entry, line, column):
        return at, []
    word, start = _word_before(line, column)
    if not word:
        return at, []
    loops = _loops_at(doc, entry, number, line, column, context)
    return line_start + start, _expression_candidates(word, loops, context)


def _locate(doc: Doc, at: int):
    """The template text around `at`: (entry, line number or value key, the line's text, the column,
    the line's document offset) - None outside every template."""
    for entry in doc.entries.values():
        if entry.kind == "text" and entry.body is not None:
            body = doc.templates.get(entry.name, "")
            for number, line in enumerate(body.split("\n")):
                start = entry.body.offset(number, 0)
                if start <= at <= start + len(line):
                    return entry, number, line, at - start, start
        elif entry.kind == "row":
            rows = doc.templates.get(entry.name) or []
            for (number, column), scalar in entry.values.items():
                value = rows[number - 1][column]
                for index, line in enumerate(value.split("\n")):
                    start = scalar.offset(index, 0)
                    if start <= at <= start + len(line):
                        return entry, (number, column), line, at - start, start
    return None


def _in_expression(entry: Entry, line: str, column: int) -> bool:
    """The cursor is inside an expression: an open or closed hole, or an @if / `where` predicate."""
    runs = tempemplator.brace_runs(line[:column])
    if runs and runs[-1][0] == "lone" and line[runs[-1][1]] == "{":
        return True                                             # typing inside a hole not yet closed
    if any(kind == "lone" and line[start] == "{" for kind, start, _end in runs[-2:]) \
            and runs[-1][0] == "text":
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


def _loops_at(doc: Doc, entry: Entry, number, line: str, column: int, context: Context) -> dict:
    """{loop var: its table's columns (None = a range / unknown)} active at the cursor - the enclosing
    block @for loops of this text template + an inline @for on the cursor's own line."""
    loops = {}
    if entry.kind != "text":
        return loops
    stack = []
    for current in doc.templates.get(entry.name, "").split("\n")[:number]:
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


def _expression_candidates(word: str, loops: dict, context: Context) -> list:
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
        names = set(loops) | {"_params", "_rule"} | set(context.fields or ())
        names.discard("_db")
        return [f"${n}" for n in _prefixed(head, sorted(names))]
    pool = list(expr.function_names()) + ["and", "or", "not", "in"] + sorted(context.tables or ())
    return [w for w in _prefixed(word, pool) if w.lower() != word.lower()]


def _prefixed(stem: str, pool) -> list:
    stem = stem.lower()
    return [item for item in pool if str(item).lower().startswith(stem) and str(item).lower() != stem]


# --- the live session (the view's state, Tk-free) ---------------------------------------------------- #
def is_templates_file(path: str) -> bool:
    """A chain-reaction templates file - `chain_reactions/templates.yaml` in any tier - opens in the
    template mode."""
    import os
    parts = os.path.normcase(os.path.abspath(path)).split(os.sep)
    return parts[-1:] == ["templates.yaml"] and parts[-2:-1] == ["chain_reactions"]


class Session:
    """The builder's live context over the ACTIVE config: the compiled rules (reactions.csv), the
    run-plan's hooks and the Database each one sees (loaded once per hook - `reload()` refreshes),
    the project params. The view is a thin shell over it: `check` = the lint placed on the document,
    `preview_text` = one fire for one row, as text."""

    def __init__(self):
        self.reload()

    def reload(self) -> None:
        from pipeline5 import config
        from pipeline5.phases.chain_reactions import engine
        from pipeline5.systems import catalog
        self.notes = []                               # what could not load - shown, never raised
        try:
            rows = config.load_reactions()
        except Exception as error:  # noqa: BLE001 - the engine reports rx_rules_unreadable; so do we
            rows = []
            self.notes.append(f"reactions.csv does not load: {error}")
        self.rules, findings = engine.compile_rules(rows)
        self.notes += [f"{f.type}: {f.detail}" for f in findings]
        active = config.active_system()
        system = catalog.by_id(active[0]) if active else None
        self.hooks = dict(getattr(system, "reaction_hooks", None) or {})
        try:
            self.params = config.load_params()
        except Exception as error:  # noqa: BLE001
            self.params = {}
            self.notes.append(f"project params do not load: {error}")
        self._databases = {}

    def database(self, hook: str):
        """The Database `hook` sees (None: database-less, or not loadable - noted)."""
        if hook not in self._databases:
            loader = self.hooks.get(hook)
            try:
                self._databases[hook] = loader() if loader else None
            except Exception as error:  # noqa: BLE001 - e.g. nothing staged yet in this project
                self._databases[hook] = None
                self.notes.append(f"the {hook} database does not load: {error}")
        return self._databases[hook]

    def rule_labels(self) -> list:
        return ["(no rule - the syntax checks only)"] + [
            f"{r.name}  ·  {r.fire_when}  ·  {r.action} -> {r.target}" for r in self.rules]

    def rule(self, index: int):
        """The rule at `index` of `rule_labels()` (0 = no rule)."""
        return self.rules[index - 1] if 1 <= index <= len(self.rules) else None

    def row_count(self, rule) -> int:
        """How many source rows the rule's hook offers (0: source-less, or no such table there)."""
        database = self.database(rule.fire_when) if rule is not None else None
        if rule is None or not rule.source_table or database is None or rule.source_table not in database:
            return 0
        return len(database[rule.source_table])

    def context(self, rule) -> Context:
        """The completion context for `rule` (None: the document alone)."""
        if rule is None:
            return Context(params=self.params)
        database = self.database(rule.fire_when)
        tables = {} if database is None else {n: database[n].effective_columns() for n in database.names()}
        fields = None
        if not rule.source_table or rule.source_table in tables:
            fields = frozenset({"_params", "_rule", "_db"} | set(tables.get(rule.source_table, ())))
        return Context(fields=fields, tables=tables, params=self.params)

    def check(self, doc: Doc, rule) -> list:
        """engine.lint on the document (the rule's context when one is chosen), placed."""
        from pipeline5.phases.chain_reactions import engine
        if doc.error is not None:
            return place(doc, [])
        database = self.database(rule.fire_when) if rule is not None else None
        hooks = tuple(self.hooks) or None
        return place(doc, engine.lint(doc.templates, rule, database, hooks))

    def preview_text(self, doc: Doc, rule, row: int) -> str:
        """What ONE fire of `rule` would do for source row `row` (engine.preview), as text."""
        from pipeline5.phases.chain_reactions import engine
        if rule is None:
            return "Choose a rule to preview what a fire would do for one of its rows."
        if doc.error is not None:
            return "templates.yaml does not load - fix it to preview."
        shown = engine.preview(rule, row, templates=doc.templates, params=self.params,
                               database=self.database(rule.fire_when))
        lines = []
        if shown.note:
            lines.append(shown.note)
        if not shown.matched and shown.problem is None and not shown.note:
            lines.append("(this row does NOT match the rule's condition - a fire skips it; rendered anyway:)")
        if shown.problem is not None:
            lines.append(f"{shown.problem[0]}: {shown.problem[1]}")
        if rule.action == "file" and shown.problem is None and not shown.note:
            lines += [f"APPEND to {shown.path}:", shown.text]
        elif shown.rows:
            lines.append(f"SPAWN into {rule.target}:")
            lines += ["  " + ", ".join(f"{k}={v!r}" for k, v in row_values.items()) for row_values in shown.rows]
        return "\n".join(lines)
