"""The tokenizer + recursive-descent thunk-compiler for the unified expression engine (M-E1).

A clean SUPERSET of rule_expr's parser. The shape is identical (a `_Parser` that compiles each production
to a `lambda ctx: value` thunk - lazy, cached), but the grammar grows:

  * `$field` / `$obj.key`     - field refs (no bare-word fields). Dotted access into a dict cell is
                                SILENT-EMPTY on a missing sub-key.
  * Scope validation          - an unknown top-level `$x` raises a located ExprError at COMPILE.
  * the rule_expr operators    - ~ /re/ (IGNORECASE), = != , in [..], numeric > >= < <= , and/or/not/().
  * functions                  - clean/concat/join/numeric/isdigit/len/present/blank/startswith/extract,
                                if/coalesce, let, and the data funcs where/first/lookup/unique/count/node_of.

NO arithmetic operators (+ - * /) - arithmetic is intentionally not in the grammar.

The thunk a production returns is `fn(ctx) -> value`; predicates bottom out in `truthy`. The parser is
re-entrant for `let` (it threads a Scope through a per-binding compile so a body sees earlier binds).
"""
from __future__ import annotations

import re

from . import data, runtime
from .errors import ExprError
from .scope import Scope

# --- tokenizer ---------------------------------------------------------------------------------- #
# Ordering matters: $field (incl. dotted) before ident; ':=' before the ':' that starts a slice/spec;
# 'slice' (a bare a:b / :b / a: / index) is recognised in extract's 3rd-arg position by the parser,
# so the tokenizer emits the raw pieces (number / ':' ) and the parser assembles them.
_TOKEN_RE = re.compile(
    r"""\s+
      | (?P<field>\$[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)
      | (?P<regex>/(?:\\.|[^/\\])*/)
      | (?P<string>"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')
      | (?P<number>-?\d+(?:\.\d+)?)
      | (?P<bind>:=)
      | (?P<op>!=|>=|<=|[=<>~(),\[\];:])
      | (?P<ident>[A-Za-z_]\w*)
    """,
    re.VERBOSE,
)

# host / leaf funcs (non-data). Data funcs are dispatched separately (they take a table NAME word).
_FUNCS = frozenset({
    "clean", "strip", "concat", "join", "numeric", "isdigit", "len", "present", "blank",
    "startswith", "extract", "regex_replace", "if", "coalesce", "let",
})
_DATA_FUNCS = frozenset({"where", "first", "lookup", "unique", "count", "node_of"})
_KEYWORDS = frozenset({"and", "or", "not", "in"})


def _tokenize(text: str) -> list:
    toks, pos = [], 0
    for m in _TOKEN_RE.finditer(text):
        if m.start() != pos:
            raise ExprError(f"unexpected character at {pos} in {text!r}")
        pos = m.end()
        kind = m.lastgroup
        if kind is not None:                       # None => the whitespace alternative
            toks.append((kind, m.group()))
    if pos != len(text):
        raise ExprError(f"unexpected character at {pos} in {text!r}")
    return toks


def _unescape(s: str) -> str:
    return s.replace('\\"', '"').replace("\\'", "'").replace("\\\\", "\\")


def _field_thunk(name: str):
    """A `$field` reference. `name` is without the leading '$'. Dotted -> a dict drill that is
    SILENT-EMPTY on a missing sub-key (returns "" at EVAL, never throws)."""
    if "." not in name:
        return lambda ctx: ctx.get(name, "")
    head, *rest = name.split(".")

    def thunk(ctx):
        cur = ctx.get(head, "")
        for key in rest:
            if isinstance(cur, dict):
                cur = cur.get(key, "")
            else:
                return ""
        return cur
    return thunk


# --- parser (compiles to a thunk fn(ctx) -> value) ---------------------------------------------- #
class _Parser:
    def __init__(self, toks, src, scope: Scope | None):
        self.toks, self.i, self.src, self.scope = toks, 0, src, scope

    def _peek(self):
        return self.toks[self.i] if self.i < len(self.toks) else (None, None)

    def _next(self):
        tok = self.toks[self.i]
        self.i += 1
        return tok

    def _eat(self, text):
        if self._peek()[1] != text:
            raise ExprError(f"expected {text!r} in {self.src!r}")
        return self._next()

    def parse(self):
        fn = self._or()
        if self.i != len(self.toks):
            raise ExprError(f"trailing tokens in {self.src!r}")
        return fn

    # --- boolean layer (verbatim rule_expr structure) --- #
    def _or(self):
        left = self._and()
        while self._peek() == ("ident", "or"):
            self._next()
            right = self._and()
            left = (lambda l, r: lambda ctx: runtime.truthy(l(ctx)) or runtime.truthy(r(ctx)))(left, right)
        return left

    def _and(self):
        left = self._not()
        while self._peek() == ("ident", "and"):
            self._next()
            right = self._not()
            left = (lambda l, r: lambda ctx: runtime.truthy(l(ctx)) and runtime.truthy(r(ctx)))(left, right)
        return left

    def _not(self):
        if self._peek() == ("ident", "not"):
            self._next()
            inner = self._not()
            return lambda ctx: not runtime.truthy(inner(ctx))
        return self._comparison()

    def _comparison(self):
        left = self._value()
        kind, val = self._peek()
        if val == "~":
            self._next()
            rk, rx = self._next()
            if rk != "regex":
                raise ExprError(f"'~' needs a /regex/ in {self.src!r}")
            pat = re.compile(rx[1:-1], re.IGNORECASE)
            return lambda ctx: bool(pat.search(runtime.s(left(ctx))))
        if val in ("=", "!="):
            self._next()
            right = self._value()
            if val == "=":
                return lambda ctx: runtime.s(left(ctx)) == runtime.s(right(ctx))
            return lambda ctx: runtime.s(left(ctx)) != runtime.s(right(ctx))
        if val in (">", ">=", "<", "<="):
            op = self._next()[1]
            right = self._value()
            return lambda ctx: runtime.num_cmp(left(ctx), right(ctx), op)
        if (kind, val) == ("ident", "in"):
            self._next()
            items = self._list()
            return lambda ctx: runtime.s(left(ctx)) in [runtime.s(it(ctx)) for it in items]
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

    # --- value layer --- #
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
        if kind == "field":
            self._next()
            name = val[1:]                                   # drop the leading '$'
            top = name.split(".", 1)[0]
            if self.scope is not None and top not in self.scope:
                raise ExprError(f"unknown field ${top} (not in scope) in {self.src!r}")
            return _field_thunk(name)
        if kind == "regex":
            raise ExprError(f"a /regex/ is only valid after '~' or in extract(), in {self.src!r}")
        if val == "(":
            self._next()
            inner = self._or()
            self._eat(")")
            return inner
        if kind == "ident":
            name = self._next()[1]
            if name in _KEYWORDS:
                raise ExprError(f"unexpected keyword {name!r} in {self.src!r}")
            if self._peek()[1] == "(":
                return self._call(name)
            raise ExprError(f"bare word {name!r} (a function name or and/or/not/in expected) in {self.src!r}")
        raise ExprError(f"unexpected token {val!r} in {self.src!r}")

    # --- function dispatch --- #
    def _call(self, name):
        if name in _DATA_FUNCS:
            return self._data_call(name)
        if name not in _FUNCS:
            raise ExprError(f"unknown function {name!r} in {self.src!r}")
        if name == "extract":
            return self._extract()
        if name == "regex_replace":
            return self._regex_replace()
        if name == "let":
            return self._let()
        if name == "if":
            return self._if()
        if name == "startswith":
            return self._startswith()
        # variadic / single-arg funcs share a flat arg list
        self._eat("(")
        args = self._args()
        self._eat(")")
        return self._apply(name, args)

    def _args(self):
        """A comma-separated list of value/predicate expressions, possibly empty."""
        args = []
        if self._peek()[1] != ")":
            args.append(self._or())
            while self._peek()[1] == ",":
                self._next()
                args.append(self._or())
        return args

    def _apply(self, name, args):
        if name == "numeric":
            self._arity(name, args, 1)
            a = args[0]
            return lambda ctx: runtime.is_numeric(a(ctx))
        if name == "len":
            self._arity(name, args, 1)
            a = args[0]
            return lambda ctx: float(len(runtime.s(a(ctx))))
        if name == "isdigit":
            self._arity(name, args, 1)
            a = args[0]
            return lambda ctx: runtime.s(a(ctx)).isdigit()
        if name == "present":
            self._arity(name, args, 1)
            a = args[0]
            return lambda ctx: bool(runtime.s(a(ctx)).strip())
        if name == "blank":
            self._arity(name, args, 1)
            a = args[0]
            return lambda ctx: not runtime.s(a(ctx)).strip()
        if name == "clean":
            self._arity(name, args, 1)
            a = args[0]
            return lambda ctx: runtime.clean(a(ctx))
        if name == "strip":
            self._arity(name, args, 1)
            a = args[0]
            return lambda ctx: runtime.s(a(ctx)).strip()    # trim only (faithful for a RESULT value; cf. clean())
        if name == "concat":
            return lambda ctx: "".join(runtime.s(a(ctx)) for a in args)
        if name == "join":
            if not args:
                raise ExprError(f"join() needs a separator in {self.src!r}")
            sep, parts = args[0], args[1:]
            return lambda ctx: runtime.s(sep(ctx)).join(runtime.s(p(ctx)) for p in parts)
        if name == "coalesce":
            return self._coalesce(args)
        raise ExprError(f"unknown function {name!r} in {self.src!r}")

    def _arity(self, name, args, n):
        if len(args) != n:
            raise ExprError(f"{name}() takes {n} arg(s), got {len(args)} in {self.src!r}")

    def _coalesce(self, args):
        def thunk(ctx):
            for a in args:
                v = a(ctx)
                if runtime.s(v) != "":
                    return v
            return ""
        return thunk

    def _if(self):
        self._eat("(")
        cond = self._or()
        self._eat(",")
        then = self._or()
        self._eat(",")
        otherwise = self._or()
        self._eat(")")
        return lambda ctx: then(ctx) if runtime.truthy(cond(ctx)) else otherwise(ctx)

    def _startswith(self):
        self._eat("(")
        target = self._value()
        self._eat(",")
        prefix = self._value()
        self._eat(")")
        return lambda ctx: runtime.s(target(ctx)).startswith(runtime.s(prefix(ctx)))

    def _extract(self):
        """extract($f, /re/ [, SLICE]) - capture-first (implicit IGNORECASE). The optional 3rd arg is a
        SLICE (a:b / :b / a: / a) applied to group(1) (if any groups) else group(0)."""
        self._eat("(")
        field = self._value()
        self._eat(",")
        rk, rx = self._next()
        if rk != "regex":
            raise ExprError(f"extract: 2nd arg must be a /regex/ in {self.src!r}")
        pat = re.compile(rx[1:-1], re.IGNORECASE)
        slice_spec = None
        if self._peek()[1] == ",":
            self._next()
            slice_spec = self._slice()
        self._eat(")")
        return lambda ctx: runtime.extract(field(ctx), pat, slice_spec)

    def _regex_replace(self):
        """regex_replace(value, /re/, replacement) - every match of the (implicit-IGNORECASE) regex in
        `value` replaced by `replacement` (re.sub semantics: \\1 group backrefs work). `value` and
        `replacement` are full expressions; the pattern is a /regex/ literal (like extract's)."""
        self._eat("(")
        value = self._or()
        self._eat(",")
        rk, rx = self._next()
        if rk != "regex":
            raise ExprError(f"regex_replace: 2nd arg must be a /regex/ in {self.src!r}")
        pat = re.compile(rx[1:-1], re.IGNORECASE)
        self._eat(",")
        replacement = self._or()
        self._eat(")")
        return lambda ctx: runtime.regex_replace(value(ctx), pat, runtime.s(replacement(ctx)))

    def _slice(self):
        """Parse a slice/index: `a:b`, `:b`, `a:`, or a bare `a` (an index). Returns (lo, hi, is_index)."""
        lo = hi = None
        has_colon = False
        kind, val = self._peek()
        if kind == "number":
            lo = int(self._next()[1])
        if self._peek()[1] == ":":
            self._next()
            has_colon = True
            if self._peek()[0] == "number":
                hi = int(self._next()[1])
        if not has_colon:
            if lo is None:
                raise ExprError(f"extract: bad SLICE in {self.src!r}")
            return (lo, None, True)                          # a bare index
        return (lo, hi, False)                               # a real slice [lo:hi]

    # --- let(a := e1, b := f($a); body) --- #
    def _let(self):
        self._eat("(")
        names, binders = [], []
        scope = self.scope
        # bindings: NAME := expr ( , NAME := expr )* ; body
        while True:
            nk, nv = self._next()
            if nk != "ident":
                raise ExprError(f"let: expected a binding name in {self.src!r}")
            self._eat(":=")
            # compile the binding expr in the CURRENT (accumulating) scope
            sub = _Parser(self.toks, self.src, scope)
            sub.i = self.i
            expr_fn = sub._or()
            self.i = sub.i
            names.append(nv)
            binders.append((nv, expr_fn))
            if scope is not None:
                scope = scope.with_names([nv])
            if self._peek()[1] == ";":
                self._next()
                break
            self._eat(",")
        # body compiled in the scope extended with all bound names
        body_parser = _Parser(self.toks, self.src, scope)
        body_parser.i = self.i
        body_fn = body_parser._or()
        self.i = body_parser.i
        self._eat(")")

        def thunk(ctx):
            local = dict(ctx)
            for nm, fn in binders:
                local[nm] = fn(local)                        # bind-once, sequential, sees earlier binds
            return body_fn(local)
        return thunk

    # --- data funcs (table-name word + per-row predicate) --- #
    def _table_name(self):
        kind, val = self._next()
        if kind == "string":
            return _unescape(val[1:-1])
        if kind == "ident":
            return val
        raise ExprError(f"expected a table name in {self.src!r}")

    def _pred_in_row_scope(self):
        """Compile a predicate against a PER-ROW scope (scope=None so any $col resolves to the row cell)."""
        sub = _Parser(self.toks, self.src, None)
        sub.i = self.i
        fn = sub._or()
        self.i = sub.i
        return fn

    def _data_call(self, name):
        self._eat("(")
        if name == "where" or name == "first":
            table = self._table_name()
            pred = None
            if self._peek()[1] == ",":
                self._next()
                pred = self._pred_in_row_scope()
            self._eat(")")
            if name == "where":
                return lambda ctx: data.where(ctx, table, _binder(pred))
            return lambda ctx: data.first(ctx, table, _binder(pred))
        if name == "count":
            table = self._table_name()
            pred = None
            if self._peek()[1] == ",":
                self._next()
                pred = self._pred_in_row_scope()
            self._eat(")")
            return lambda ctx: data.count(ctx, table, _binder(pred))
        if name == "unique":
            col = self._col_word()
            self._eat(",")
            table = self._table_name()
            self._eat(")")
            return lambda ctx: data.unique(ctx, col, table)
        if name == "lookup":
            table = self._table_name()
            self._eat(",")
            key_col = self._col_word()
            self._eat(",")
            key_val = self._value()
            self._eat(",")
            val_col = self._col_word()
            self._eat(")")
            return lambda ctx: data.lookup(ctx, table, key_col, key_val(ctx), val_col)
        if name == "node_of":
            bit = self._value()
            self._eat(",")
            table = self._table_name()
            self._eat(")")
            return lambda ctx: data.node_of(ctx, bit(ctx), table)
        raise ExprError(f"unknown data function {name!r} in {self.src!r}")

    def _col_word(self):
        """A column name - a bare ident or a quoted string (columns are structural, not $fields)."""
        kind, val = self._next()
        if kind == "string":
            return _unescape(val[1:-1])
        if kind == "ident":
            return val
        raise ExprError(f"expected a column name in {self.src!r}")


def _binder(pred_fn):
    """A per-row predicate adapter: the data layer passes the row dict as ctx, scope-less $col lookups
    resolve against it. `pred_fn` already closes over the row via its ctx arg, so just return it."""
    return pred_fn


def compile_expr(text: str, scope: Scope | None):
    """Tokenize + parse `text` into a thunk fn(ctx) -> value. Raises a located ExprError."""
    return _Parser(_tokenize(text), text, scope).parse()


def referenced_fields(text: str) -> set:
    """The set of TOP-LEVEL `$field` names referenced anywhere in `text` (a tokenizer scan, no parse) -
    including those nested inside function-call args. Used by render's keep/strict modes to decide
    missing-ness over the WHOLE hole, not just a bare `$field` hole. A malformed token -> {} (the
    compile step reports the real error)."""
    try:
        toks = _tokenize(text)
    except ExprError:
        return set()
    return {val[1:].split(".", 1)[0] for kind, val in toks if kind == "field"}
