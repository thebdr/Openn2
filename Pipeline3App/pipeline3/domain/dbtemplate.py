"""Two small grammars for the config-driven data-block subsystem (phase 520), both validate-and-halt:

1. `render(template, ctx)` — a PEP-3101 format string (`{name}` / `{name:spec}`) over a context dict,
   restricted to bare field names (no attribute/index access, no positional args); a numeric format spec
   coerces the (string) value first, so `{cabinet:03d}` works on the cell `'1'` -> `'001'`.
2. `compile_for_each(expr)` -> `ForEach` — the iteration DSL:
       (blank)                                    -> a single literal item
       row [where <pred>]                          -> one per IODatabase row (optionally filtered)
       <var> in unique(<column>) [where <pred>]    -> one per DISTINCT value of <column>, bound to <var>
   `<pred>` is a boolean over a row: `numeric(col)`, `col = "x"`, `col != "x"`, `col in ["a","b"]`,
   `col ~ /regex/`, `not P`, `P and Q`, `P or Q`, `( P )`.

Both raise `DbTemplateError` on a bad template / expression / unknown field; the caller logs it and HALTS
the pipeline before the Openn3 import ever sees a malformed name. Pure + data-independent.
"""
from __future__ import annotations
import re
import string


class DbTemplateError(ValueError):
    """A malformed template or for_each expression (-> logged + pipeline halt)."""


# --- 1. PEP-3101 value/name templates ----------------------------------------------------------- #
_FIELD_RE = re.compile(r"[A-Za-z_]\w*\Z")


class _SafeFormatter(string.Formatter):
    """str.format() restricted to `{name}` / `{name:spec}` over a dict — no `{0}`, no `{a.b}`/`{a[i]}`."""

    def get_value(self, key, args, kwargs):
        if isinstance(key, int):
            raise DbTemplateError("positional fields {0} are not allowed; use {name}")
        if not _FIELD_RE.match(key or ""):
            raise DbTemplateError(f"invalid template field {{{key}}} (use a bare {{name}})")
        if key not in kwargs:
            raise DbTemplateError(f"unknown template field {{{key}}}")
        return kwargs[key]

    def format_field(self, value, format_spec):
        last = format_spec[-1] if format_spec else ""
        try:
            if last and last in "dboxXc":
                value = int(str(value).strip())
            elif last and last in "eEfFgG%":
                value = float(str(value).strip())
            return format(value, format_spec)
        except (ValueError, TypeError) as e:
            raise DbTemplateError(f"bad format spec {format_spec!r} for value {value!r}: {e}")


_FMT = _SafeFormatter()


def render(template, ctx: dict) -> str:
    """Render a PEP-3101 `template` against `ctx`; raise DbTemplateError on an unknown field / bad spec."""
    try:
        return _FMT.vformat(str(template if template is not None else ""), (), ctx)
    except DbTemplateError:
        raise
    except (KeyError, IndexError, ValueError) as e:
        raise DbTemplateError(f"bad template {template!r}: {e}")


def template_fields(template) -> set:
    """The bare field names a template references (for up-front validation)."""
    out = set()
    for _lit, field, _spec, _conv in string.Formatter().parse(str(template or "")):
        if field:
            out.add(field)
    return out


# --- 2. the for_each iteration DSL -------------------------------------------------------------- #
_TOK_RE = re.compile(r"""
      \s+
    | (?P<str>"[^"]*")
    | (?P<re>/[^/]*/)
    | (?P<punc>!=|=|~|\(|\)|\[|\]|,)
    | (?P<word>[A-Za-z_]\w*)
""", re.VERBOSE)
_KEYWORDS = {"row", "in", "unique", "where", "numeric", "not", "and", "or"}


def _tokenize(expr: str) -> list:
    toks, i = [], 0
    for m in _TOK_RE.finditer(expr):
        if m.start() != i:
            raise DbTemplateError(f"for_each: unexpected character {expr[i:m.start()]!r}")
        i = m.end()
        g = m.lastgroup
        if g == "str":
            toks.append(("str", m.group()[1:-1]))
        elif g == "re":
            toks.append(("re", m.group()[1:-1]))
        elif g == "punc":
            toks.append((m.group(), m.group()))
        elif g == "word":
            w = m.group()
            toks.append(("kw" if w in _KEYWORDS else "name", w))
    if i != len(expr):
        raise DbTemplateError(f"for_each: unexpected character {expr[i:]!r}")
    return toks


def _cell(row, col) -> str:
    return str(row.get(col, "") if row else "").strip()


class ForEach:
    """A compiled iteration expression. `evaluate(rows)` yields `(binding, rep_row)`:
      - literal: one `({}, None)`;
      - row:     one `({}, row)` per row passing the predicate;
      - unique:  one `({var: value}, first_row)` per DISTINCT value of `column` (rows pre-filtered by the
                 predicate; a `|`-multi-valued cell is split), in first-seen order.
    `columns` is every column the expression names (the engine checks them against the real row keys)."""

    def __init__(self, kind, var, column, predicate, columns, source):
        self.kind, self.var, self.column = kind, var, column
        self._pred, self.columns, self.source = predicate, columns, source

    def evaluate(self, rows):
        rows = rows or []
        if self.kind == "literal":
            yield {}, None
            return
        keep = (r for r in rows if self._pred(r)) if self._pred else iter(rows)
        if self.kind == "row":
            for r in keep:
                yield {}, r
            return
        seen = set()                                          # kind == "unique"
        for r in keep:
            for v in (_cell(r, self.column).split("|") if "|" in _cell(r, self.column) else [_cell(r, self.column)]):
                v = v.strip()
                if v and v not in seen:
                    seen.add(v)
                    yield {self.var: v}, r

    def __repr__(self):
        return f"ForEach({self.source!r})"


class _Parser:
    def __init__(self, toks):
        self.toks, self.pos, self.cols = toks, 0, set()

    def _peek(self):
        return self.toks[self.pos] if self.pos < len(self.toks) else (None, None)

    def _take(self):
        t = self._peek()
        self.pos += 1
        return t

    def _expect(self, val):
        t = self._take()
        if val not in (t[0], t[1]):
            raise DbTemplateError(f"for_each: expected {val!r}, got {t[1]!r}")
        return t

    def _name(self):
        t = self._take()
        if t[0] != "name":
            raise DbTemplateError(f"for_each: expected a column name, got {t[1]!r}")
        self.cols.add(t[1])
        return t[1]

    # for_each := (empty) | row [where P] | <var> in unique(<col>) [where P]
    def parse(self):
        if not self.toks:
            return ForEach("literal", None, None, None, set(), "")
        head, val = self._peek()
        if (head, val) == ("kw", "row"):
            self._take()
            pred = self._where()
            self._end()
            return ForEach("row", None, None, pred, self.cols, _join(self.toks))
        if head == "name":
            var = self._take()[1]
            self._expect("in")
            self._expect("unique")
            self._expect("(")
            col = self._name()
            self._expect(")")
            pred = self._where()
            self._end()
            return ForEach("unique", var, col, pred, self.cols, _join(self.toks))
        raise DbTemplateError(f"for_each: expected 'row' or '<var> in unique(col)', got {val!r}")

    def _end(self):
        if self.pos != len(self.toks):
            raise DbTemplateError(f"for_each: trailing tokens {[t[1] for t in self.toks[self.pos:]]}")

    def _where(self):
        if self._peek() == ("kw", "where"):
            self._take()
            return self._or()
        return None

    # P := or ; or := and ('or' and)* ; and := not ('and' not)* ; not := ['not'] atom
    def _or(self):
        f = self._and()
        while self._peek() == ("kw", "or"):
            self._take()
            g, h = f, self._and()
            f = (lambda a, b: (lambda r: a(r) or b(r)))(g, h)
        return f

    def _and(self):
        f = self._not()
        while self._peek() == ("kw", "and"):
            self._take()
            g, h = f, self._not()
            f = (lambda a, b: (lambda r: a(r) and b(r)))(g, h)
        return f

    def _not(self):
        if self._peek() == ("kw", "not"):
            self._take()
            inner = self._not()
            return (lambda a: (lambda r: not a(r)))(inner)
        return self._atom()

    # atom := ( P ) | numeric(col) | col (= | != | in | ~) rhs
    def _atom(self):
        if self._peek() == ("(", "("):
            self._take()
            f = self._or()
            self._expect(")")
            return f
        if self._peek() == ("kw", "numeric"):
            self._take()
            self._expect("(")
            col = self._name()
            self._expect(")")
            return (lambda c: (lambda r: _cell(r, c).isdigit()))(col)   # bare non-neg int (skips -1/blank)
        col = self._name()
        _t, opv = self._take()                                # op value (= != ~ punc, or the 'in' keyword)
        if opv == "=":
            val = self._str()
            return (lambda c, v: (lambda r: _cell(r, c) == v))(col, val)
        if opv == "!=":
            val = self._str()
            return (lambda c, v: (lambda r: _cell(r, c) != v))(col, val)
        if opv == "~":
            rx = self._regex()
            return (lambda c, p: (lambda r: p.search(_cell(r, c)) is not None))(col, rx)
        if opv == "in":
            self._expect("[")
            vals = {self._str()}
            while self._peek() == (",", ","):
                self._take()
                vals.add(self._str())
            self._expect("]")
            return (lambda c, s: (lambda r: _cell(r, c) in s))(col, frozenset(vals))
        raise DbTemplateError(f"for_each: expected =, !=, ~ or in after {col!r}, got {opv!r}")

    def _str(self):
        t = self._take()
        if t[0] != "str":
            raise DbTemplateError(f'for_each: expected a "quoted" value, got {t[1]!r}')
        return t[1]

    def _regex(self):
        t = self._take()
        if t[0] != "re":
            raise DbTemplateError(f"for_each: expected a /regex/, got {t[1]!r}")
        try:
            return re.compile(t[1])
        except re.error as e:
            raise DbTemplateError(f"for_each: bad regex /{t[1]}/: {e}")


def _join(toks):
    return " ".join(t[1] for t in toks)


def compile_for_each(expr) -> ForEach:
    """Compile a for_each expression. Raise DbTemplateError on a syntax error."""
    return _Parser(_tokenize(str(expr or "").strip())).parse()
