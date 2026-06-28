"""rule_expr - a small, reusable, config-rule expression engine (predicates + result templates).

It is deliberately standalone (no pipeline imports) so any config-driven ruleset can use it: ph200's
script-type / gate rules today, more tomorrow. Two entry points:

    test(predicate, ctx) -> bool        # evaluate a boolean condition (a rule's `when`)
    render(template, ctx) -> str        # interpolate {value-expr} tokens (a rule's result)

`ctx` is a plain dict of field -> value (strings). Compiled expressions are cached.

==============================================================================================
SYNTAX GUIDE
==============================================================================================

A PREDICATE is a boolean expression:

    or-expr   := and-expr ( "or"  and-expr )*
    and-expr  := not-expr ( "and" not-expr )*
    not-expr  := "not" not-expr | comparison
    comparison:= value [ OP rhs ]
    value     := number | string | func-call | FIELD | "(" or-expr ")"

OPERATORS (a `value` with no operator is taken on its truthiness - non-empty string / non-zero number):
    field ~ /regex/        case-insensitive regex SEARCH (substring/anywhere)         -> bool
    field = "text"         string equality                                            -> bool
    field != "text"        string inequality                                          -> bool
    field in ["a","b"]     membership (string compare)                                -> bool
    field > N   >= < <=     numeric comparison (both sides coerced to float; bad -> False)

FUNCTIONS:
    numeric(EXPR)          True if EXPR coerces to a float                            -> bool
    len(EXPR)              character length of EXPR                                   -> number
    isdigit(EXPR)          True if str(EXPR) is all digits (non-empty)               -> bool
    present(FIELD)         True if the field is non-empty after strip                 -> bool
    blank(FIELD)           True if the field is empty/whitespace                      -> bool
    extract(FIELD, /regex/, PART)   the matched substring's PART, "" if no match      -> str
                           PART = last (last char of the match) | first | group<N>

VALUES / LITERALS:
    "double-quoted string"     a string literal
    123  / 1.5                 a number literal
    /regex/                    a regex literal (only valid on the right of `~`, or as extract's 2nd arg)
    bareword                   a FIELD reference -> ctx.get(name, "")

A RESULT TEMPLATE is literal text with `{value-expr}` holes, each evaluated and stringified:

    "E{extract(d2,/CH./,last)}/2"     ->  "E1/2"   (when d2 has "...CH.1...")
    "{type_hw}"                        ->  the type_hw field
    "{INPUT_REQUIRED}"                 ->  ctx["INPUT_REQUIRED"] (the caller supplies the sentinel)
    "KQ"                               ->  "KQ"     (no holes -> literal)

NOTES
    * Matching is case-insensitive; the caller is responsible for any text CLEANING (collapse whitespace,
      strip control chars) before building ctx - the engine matches whatever strings ctx holds.
    * In a CSV, a `when`/`type` cell containing a comma (e.g. an extract() or an `in [..]`) must be quoted.
    * To extend the grammar, add a function in `_Parser._call` or an operator in `_Parser._comparison`;
      keep this guide in sync.
"""
from __future__ import annotations

import re

__all__ = ["test", "render", "RuleError"]


class RuleError(ValueError):
    """A malformed rule expression (located message)."""


# --- tokenizer ---------------------------------------------------------------------------------- #
_TOKEN_RE = re.compile(
    r"""\s+
      | (?P<regex>/(?:\\.|[^/\\])*/)
      | (?P<string>"(?:\\.|[^"\\])*")
      | (?P<number>\d+(?:\.\d+)?)
      | (?P<op>!=|>=|<=|[=<>~(),\[\]])
      | (?P<ident>[A-Za-z_]\w*)
    """,
    re.VERBOSE,
)
_FUNCS = frozenset({"numeric", "len", "isdigit", "present", "blank", "extract"})


def _tokenize(text: str) -> list:
    toks, pos = [], 0
    for m in _TOKEN_RE.finditer(text):
        if m.start() != pos:
            raise RuleError(f"unexpected character at {pos} in {text!r}")
        pos = m.end()
        kind = m.lastgroup
        if kind is not None:                       # None => the whitespace alternative
            toks.append((kind, m.group()))
    if pos != len(text):
        raise RuleError(f"unexpected character at {pos} in {text!r}")
    return toks


# --- value helpers ------------------------------------------------------------------------------ #
def _s(v) -> str:
    return "" if v is None else (v if isinstance(v, str) else str(v))


def _truthy(v) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    return bool(_s(v))


def _is_numeric(v) -> bool:
    try:
        float(_s(v))
        return True
    except ValueError:
        return False


def _num_cmp(a, b, op: str) -> bool:
    try:
        x, y = float(_s(a)), float(_s(b))
    except ValueError:
        return False
    return {">": x > y, ">=": x >= y, "<": x < y, "<=": x <= y}[op]


def _extract(text, pattern, part: str) -> str:
    m = pattern.search(_s(text))
    if not m:
        return ""
    whole = m.group(0)
    if part == "last":
        return whole[-1] if whole else ""
    if part == "first":
        return whole[0] if whole else ""
    if part.startswith("group"):
        try:
            return _s(m.group(int(part[5:])))
        except (IndexError, ValueError):
            return ""
    raise RuleError(f"extract: bad PART {part!r} (use last|first|group<N>)")


def _unescape(s: str) -> str:
    return s.replace('\\"', '"').replace("\\\\", "\\")


# --- parser (compiles to a thunk fn(ctx) -> value) ---------------------------------------------- #
class _Parser:
    def __init__(self, toks, src):
        self.toks, self.i, self.src = toks, 0, src

    def _peek(self):
        return self.toks[self.i] if self.i < len(self.toks) else (None, None)

    def _next(self):
        tok = self.toks[self.i]
        self.i += 1
        return tok

    def _eat(self, text):
        if self._peek()[1] != text:
            raise RuleError(f"expected {text!r} in {self.src!r}")
        return self._next()

    def parse(self):
        fn = self._or()
        if self.i != len(self.toks):
            raise RuleError(f"trailing tokens in {self.src!r}")
        return fn

    def _or(self):
        left = self._and()
        while self._peek() == ("ident", "or"):
            self._next()
            right = self._and()
            left = (lambda l, r: lambda ctx: _truthy(l(ctx)) or _truthy(r(ctx)))(left, right)
        return left

    def _and(self):
        left = self._not()
        while self._peek() == ("ident", "and"):
            self._next()
            right = self._not()
            left = (lambda l, r: lambda ctx: _truthy(l(ctx)) and _truthy(r(ctx)))(left, right)
        return left

    def _not(self):
        if self._peek() == ("ident", "not"):
            self._next()
            inner = self._not()
            return lambda ctx: not _truthy(inner(ctx))
        return self._comparison()

    def _comparison(self):
        left = self._value()
        kind, val = self._peek()
        if val == "~":
            self._next()
            rk, rx = self._next()
            if rk != "regex":
                raise RuleError(f"'~' needs a /regex/ in {self.src!r}")
            pat = re.compile(rx[1:-1], re.IGNORECASE)
            return lambda ctx: bool(pat.search(_s(left(ctx))))
        if val in ("=", "!="):
            self._next()
            right = self._value()
            if val == "=":
                return lambda ctx: _s(left(ctx)) == _s(right(ctx))
            return lambda ctx: _s(left(ctx)) != _s(right(ctx))
        if val in (">", ">=", "<", "<="):
            op = self._next()[1]
            right = self._value()
            return lambda ctx: _num_cmp(left(ctx), right(ctx), op)
        if (kind, val) == ("ident", "in"):
            self._next()
            items = self._list()
            return lambda ctx: _s(left(ctx)) in [_s(it(ctx)) for it in items]
        return left

    def _list(self):
        self._eat("[")
        items = []
        if self._peek()[1] != "]":
            items.append(self._value())
            while self._peek()[1] == ",":
                self._next()
                items.append(self._value())
        self._eat("]")
        return items

    def _value(self):
        kind, val = self._peek()
        if kind == "number":
            self._next()
            num = float(val)
            return lambda ctx: num
        if kind == "string":
            self._next()
            text = _unescape(val[1:-1])
            return lambda ctx: text
        if kind == "regex":
            raise RuleError(f"a /regex/ is only valid after '~' or as extract()'s 2nd arg, in {self.src!r}")
        if val == "(":
            self._next()
            inner = self._or()
            self._eat(")")
            return inner
        if kind == "ident":
            name = self._next()[1]
            if self._peek()[1] == "(":
                return self._call(name)
            return lambda ctx: ctx.get(name, "")
        raise RuleError(f"unexpected token {val!r} in {self.src!r}")

    def _call(self, name):
        if name not in _FUNCS:
            raise RuleError(f"unknown function {name!r} in {self.src!r}")
        self._eat("(")
        if name == "extract":
            fk, field = self._next()
            if fk != "ident":
                raise RuleError(f"extract: 1st arg must be a field in {self.src!r}")
            self._eat(",")
            rk, rx = self._next()
            if rk != "regex":
                raise RuleError(f"extract: 2nd arg must be a /regex/ in {self.src!r}")
            pat = re.compile(rx[1:-1], re.IGNORECASE)
            self._eat(",")
            pk, part = self._next()
            if pk != "ident":
                raise RuleError(f"extract: 3rd arg must be last|first|group<N> in {self.src!r}")
            self._eat(")")
            return lambda ctx: _extract(ctx.get(field, ""), pat, part)
        arg = self._or()
        self._eat(")")
        if name == "numeric":
            return lambda ctx: _is_numeric(arg(ctx))
        if name == "len":
            return lambda ctx: float(len(_s(arg(ctx))))
        if name == "isdigit":
            return lambda ctx: _s(arg(ctx)).isdigit()
        if name == "present":
            return lambda ctx: bool(_s(arg(ctx)).strip())
        return lambda ctx: not _s(arg(ctx)).strip()    # blank


# --- public API --------------------------------------------------------------------------------- #
_CACHE: dict = {}


def _compile(text: str):
    fn = _CACHE.get(text)
    if fn is None:
        fn = _Parser(_tokenize(text), text).parse()
        _CACHE[text] = fn
    return fn


def test(predicate: str, ctx: dict) -> bool:
    """Evaluate a boolean predicate against `ctx`. An empty/blank predicate is True (an always-match rule)."""
    p = (predicate or "").strip()
    return _truthy(_compile(p)(ctx)) if p else True


_BRACE = re.compile(r"\{([^{}]*)\}")


def render(template: str, ctx: dict) -> str:
    """Interpolate `{value-expr}` holes in `template` against `ctx`; non-brace text is copied verbatim."""
    return _BRACE.sub(lambda m: _s(_compile(m.group(1).strip())(ctx)) if m.group(1).strip() else "",
                      template or "")
