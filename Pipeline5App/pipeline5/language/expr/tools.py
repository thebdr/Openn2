"""Editor tooling over the engine (UI_REFRESH_PLAN G1): position-carrying tokens for syntax
highlighting, a compile-only lint for live squiggles, and the autocomplete word lists. Read-only over
the parser's own regex + tables - the runtime semantics are untouched, and nothing here raises on
half-typed input (an editor runs these on every keystroke).

    tokens(text)                    -> [(kind, start, end)]   kinds: field regex string number bind op
                                                              keyword func data_func ident error
    check(text, scope=None)         -> [Issue(start, end, message)]   lint ONE expression
    check_template(tpl, scope=None) -> [Issue]                 lint a render template's {holes}
    function_names() / keyword_names() / data_function_names() -> the autocomplete word lists
"""
from __future__ import annotations

from collections import namedtuple

from .errors import ExprError
from .parser import _DATA_FUNCS, _FUNCS, _KEYWORDS, _TOKEN_RE, compile_expr
from .render import _HOLE, _split_spec

Issue = namedtuple("Issue", "start end message")


def tokens(text: str) -> list:
    """The position-carrying token stream, LENIENT: an unexpected character becomes an ('error', i, i+1)
    token and the scan resumes (half-typed input must still highlight). `ident` refines to
    keyword / func / data_func by the parser's own tables."""
    out, pos = [], 0
    text = text or ""
    while pos < len(text):
        m = _TOKEN_RE.match(text, pos)
        if m is None or m.end() == pos:
            out.append(("error", pos, pos + 1))
            pos += 1
            continue
        kind = m.lastgroup
        if kind is not None:                       # None => the whitespace alternative
            if kind == "ident":
                word = m.group()
                kind = ("keyword" if word in _KEYWORDS else
                        "func" if word in _FUNCS else
                        "data_func" if word in _DATA_FUNCS else "ident")
            out.append((kind, m.start(), m.end()))
        pos = m.end()
    return out


def check(text: str, scope=None) -> list:
    """Compile-only lint of ONE expression: bad characters (precise spans), unknown top-level `$fields`
    against `scope` (precise spans), then a permissive-scope parse for syntax errors (whole-text span -
    the parser reports the message, not an offset). Blank text is clean (an empty predicate = True)."""
    text = text or ""
    if not text.strip():
        return []
    toks = tokens(text)
    issues = [Issue(s, e, "unexpected character") for kind, s, e in toks if kind == "error"]
    if scope is not None:
        for kind, s, e in toks:
            if kind == "field":
                head = text[s + 1:e].split(".", 1)[0]
                if head not in scope:
                    issues.append(Issue(s, e, f"unknown field ${head}"))
    if not any(kind == "error" for kind, _s, _e in toks):
        try:
            compile_expr(text, None)               # permissive scope: field issues reported above
        except ExprError as error:
            issues.append(Issue(0, len(text), str(error)))
    return sorted(issues)


def check_template(template: str, scope=None) -> list:
    """Lint a RENDER template: each `{hole}` body is split expr/spec exactly like render does
    (`_split_spec` - a `:03d` spec or an extract slice is never mistaken for syntax) and the expr part
    is checked with offsets into the template. Hole-free text is a verbatim literal - always clean."""
    issues = []
    for m in _HOLE.finditer(template or ""):
        body = m.group(1)
        if not body.strip():
            continue                               # {} -> "" by definition
        expr_text, _spec = _split_spec(body)
        base = m.start(1)
        issues.extend(Issue(base + i.start, base + i.end, i.message)
                      for i in check(expr_text, scope))
    return issues


def function_names() -> list:
    """Every callable name (host + data funcs), sorted - the autocomplete list."""
    return sorted(_FUNCS | _DATA_FUNCS)


def data_function_names() -> list:
    return sorted(_DATA_FUNCS)


def keyword_names() -> list:
    return sorted(_KEYWORDS)
