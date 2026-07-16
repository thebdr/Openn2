"""pipeline5.language.expr - the PL4 UNIFIED expression engine (M-E1).

A clean SUPERSET of `core/rule_expr` - the same tokenizer + recursive-descent thunk-compiler shape, the
same operator semantics, the same `{expr}` render holes and the same compiled-expr cache, GROWN into one
engine that backs every config surface PL4 has (script-type rules, DB for_each, diagnosis/interface
templates, validation predicates). `rule_expr` stays the untouched green fallback; this is built ALONGSIDE.

Three surfaces over one compiled core:

    test(predicate, ctx, scope=None) -> bool     # truthy(evaluate); an EMPTY predicate -> True
    evaluate(expr, ctx, scope=None)  -> value    # the raw value an expression computes
    render(template, ctx, scope=None, mode="empty") -> str   # interpolate {expr} holes

`ctx` is a plain dict of field -> value. A JSON object cell is a nested dict (dotted `$obj.key` drills it).
`Scope(names)` is the optional compile-time set of valid top-level `$names`. `ExprError` is the one located
failure type. Compiled expressions are cached on `(text, scope-identity)`.

==============================================================================================
SYNTAX GUIDE
==============================================================================================

FIELD REFERENCES ($-prefixed; there are NO bare-word fields):
    $name              a field ref -> ctx.get("name", "")
    $obj.key           dotted access into a JSON-object (dict) cell; a MISSING sub-key is SILENT-EMPTY
                       at eval ("" , never throws). $obj.k1.k2 drills further.
    (a bareword is ONLY a function name or one of and / or / not / in.)

SCOPE VALIDATION (compile-time):
    Scope(names)       the set of valid top-level $names. An unknown top-level $x -> a located ExprError
                       at COMPILE. scope=None => permissive (any $name; a missing field evals to "").
                       A let-bound name is added to the scope for the duration of its body.

OPERATORS (a `value` with no operator is taken on its truthiness; NO arithmetic + - * /):
    $f ~ /regex/       case-INSENSITIVE regex SEARCH (anywhere)                          -> bool
    $f = "text"        string equality                                                   -> bool
    $f != "text"       string inequality                                                 -> bool
    $f in ["a","b"]    membership (string compare)                                       -> bool
    $f > N  >= < <=    numeric comparison (both sides float-coerced; a bad coercion -> False)
    P and Q | P or Q | not P | ( ... )    boolean composition

FUNCTIONS:
    clean($f)          control chars (\\x00-\\x1f) -> space, whitespace collapsed, stripped    -> str
    strip($f)          trim leading/trailing whitespace ONLY (no collapse) - faithful for a    -> str
                       RESULT value where clean()'s internal collapse would mangle it
    concat(a, b, ...)  string-coerce and concatenate                                       -> str
    join(sep, a, ...)  string-coerce the parts and join with `sep`                         -> str
    numeric(x)         True if x coerces to a float                                        -> bool
    isdigit(x)         True if str(x) is all digits (non-empty)                            -> bool
    len(x)             character length of x                                              -> number
    present($f)        True if the field is non-empty after strip                          -> bool
    blank($f)          True if the field is empty/whitespace                               -> bool
    startswith($f, "prefix")   True if str($f) starts with the prefix                     -> bool
    extract($f, /re/ [, SLICE])   capture-first extraction (see below)                    -> str
    regex_replace(v, /re/, repl)  every match of /re/ in v replaced by repl (re.sub:      -> str
                       \\1 backrefs work; implicit IGNORECASE; no match -> v unchanged)
    if(cond, then, else)        `then` if cond is truthy, else `else`                      -> value
    coalesce(a, b, ...)         the first value non-empty after string-coercion           -> value
    let(a := e1, b := f($a); body)   sequential BIND-ONCE locals (see below)              -> value

extract - DECISION (b) CAPTURE-FIRST, implicit IGNORECASE:
    if the regex has >=1 capturing group, the result is group(1); else it is the whole match group(0).
    an OPTIONAL 3rd-arg SLICE then applies to that string:
        -1:   the last char       :3    the first 3 chars
        1:3   chars [1:3]          2     the single char at index 2
    "" when the regex doesn't match. PARITY with rule_expr: extract($f, /CH./, -1:) == the last char of
    the whole match; :1 == the first char.

let - sequential bind-once locals:
    let(a := e1, b := f($a) ; body)
    each binding's expr is evaluated ONCE, left-to-right, into a per-eval scope; a later binding and the
    body may reference an earlier one as $a. The body follows the ';'. Bound names shadow ctx fields and
    validate in the body's (extended) scope. let(...) nests.

DATA FUNCTIONS (over host DB tables passed in ctx["_db"] = {table_name: list[row-dict]}):
    where(table, pred)        the rows for which `pred` is truthy (pred is an expression run per ROW,
                              the row is the scope: $col -> that row's cell)                -> list
    first(table, pred)        the first such row, or {} when none                           -> dict
    lookup(table, key_col, key_val, val_col)   `val_col` of the first row with key_col==key_val, "" if none
    unique(col, table)        the DISTINCT non-empty values of `col` (first-seen order)     -> list
    count(table[, pred])      number of rows (optionally only those passing `pred`)         -> number
    node_of($bit, table)      the row whose [start_byte,end_byte] contains $bit's byte; {}   -> dict
    (table / column names are bare words or "quoted" - they're structural, not $fields.)

RENDER - a template is literal text with `{expr}` holes (NOT an expression itself):
    {expr}             evaluate the expr, stringify, splice in
    {expr:spec}        a Python format spec with NUMERIC COERCION: conversions d/x/X/o/b/c/n coerce via
                       int(float(value)); e/E/f/F/g/G/% via float(value). A BLANK value (None or "") STAYS
                       BLANK (emits "", no coercion). e.g. {$n:03d} on "0" or 0 -> "000"; on "" -> "".
    {} or { }          -> "" (an empty hole)
    non-brace text     copied verbatim
    A result cell with NO {} holes renders VERBATIM ("<input required>" -> "<input required>") and is
    NEVER parsed as an expression (a literal sentinel).

    MISSING-KEY MODES (the `mode` arg):
        "empty"  (default)  a missing field -> ""
        "keep"              a hole whose top-level field is NOT in ctx -> leave the literal {token} intact;
                            a present-but-empty field substitutes to ""
        "strict"            a missing field -> raise ExprError

NOTES
    * Matching is case-insensitive (~ and extract). The caller cleans text (or uses clean()) before building
      ctx - the engine matches whatever ctx holds.
    * Compiled expressions are cached on (text, scope-identity). Pass the SAME Scope object to share a cache.
"""
from __future__ import annotations

from .errors import ExprError
from .parser import compile_expr
from .render import render
from .scope import Scope
from .runtime import truthy
from .tools import Issue, check, check_template, function_names, tokens

__all__ = ["test", "evaluate", "render", "Scope", "ExprError",
           "tokens", "check", "check_template", "Issue", "function_names"]

# compiled-expr cache keyed by (text, scope-identity)
_CACHE: dict = {}


def _compile(text: str, scope: Scope | None):
    key = (text, id(scope))
    fn = _CACHE.get(key)
    if fn is None:
        fn = compile_expr(text, scope)
        _CACHE[key] = (fn, scope)                    # keep `scope` alive so its id stays valid
    else:
        fn = fn[0]
    return fn


def evaluate(expr: str, ctx: dict, scope: Scope | None = None):
    """Compile + evaluate `expr` against `ctx`; return the raw value. Raises a located ExprError."""
    return _compile(expr, scope)(ctx)


def test(predicate: str, ctx: dict, scope: Scope | None = None) -> bool:
    """Evaluate a boolean `predicate`. An empty/blank predicate is True (an always-match rule, like
    rule_expr). Otherwise the truthiness of `evaluate`."""
    p = (predicate or "").strip()
    return truthy(_compile(p, scope)(ctx)) if p else True
