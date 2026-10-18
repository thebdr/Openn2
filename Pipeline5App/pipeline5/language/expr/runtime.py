"""Runtime value helpers for the unified expression engine - the pure functions a compiled thunk calls.

Ported VERBATIM (semantics) from rule_expr's value helpers, plus the new `clean()` host func (from
fillout/classify), the capture-first `extract` (decision (b)), and the render-time format-spec coercion
(merged from identity._format_value + dbtemplate._SafeFormatter.format_field). No grammar lives here -
this is the leaf layer the parser's thunks bottom out in.
"""
from __future__ import annotations

import re

from .errors import ExprError

# --- text cleaning (host func, port of fillout/classify.clean) ----------------------------------- #
_CTRL = re.compile(r"[\x00-\x1f]")
_WS = re.compile(r"\s+")


def clean(value) -> str:
    """control chars -> space, whitespace runs collapsed, stripped (PL3's `_clean`)."""
    return _WS.sub(" ", _CTRL.sub(" ", str(value if value is not None else ""))).strip()


# --- value coercion (port of rule_expr._s / _truthy / _is_numeric / _num_cmp) -------------------- #
def s(v) -> str:
    """Coerce any value to a string; None -> "" (rule_expr._s)."""
    return "" if v is None else (v if isinstance(v, str) else str(v))


def truthy(v) -> bool:
    """rule_expr._truthy: bool as-is, a number by != 0, else non-empty string."""
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    return bool(s(v))


def is_numeric(v) -> bool:
    """True iff `v` coerces to a float (rule_expr._is_numeric)."""
    try:
        float(s(v))
        return True
    except ValueError:
        return False


def num_cmp(a, b, op: str) -> bool:
    """Numeric comparison; both sides float-coerced, a bad coercion -> False (rule_expr._num_cmp)."""
    try:
        x, y = float(s(a)), float(s(b))
    except ValueError:
        return False
    return {">": x > y, ">=": x >= y, "<": x < y, "<=": x <= y}[op]


# --- string slice (extract's optional 3rd arg) -------------------------------------------------- #
def apply_slice(text: str, spec):
    """Apply a parsed slice/index `spec` (a (lo, hi, is_index) tuple) to `text`. `is_index` -> single
    char at that index (out-of-range -> ""); else a Python slice [lo:hi]."""
    lo, hi, is_index = spec
    if is_index:
        try:
            return text[lo]
        except IndexError:
            return ""
    return text[lo:hi]


def extract(text, pattern, slice_spec) -> str:
    """Capture-first extraction (decision (b)). If `pattern` has >=1 capturing group, the result is
    group(1); otherwise it is the whole match group(0). An OPTIONAL `slice_spec` (None = no slice) is
    then applied to that string. "" on no match. Implicit IGNORECASE is baked into `pattern` by the
    parser. PARITY: with NO group + a slice, this is rule_expr's `whole[slice]` (e.g. `-1:` == last)."""
    m = pattern.search(s(text))
    if not m:
        return ""
    if pattern.groups >= 1:
        out = s(m.group(1))
    else:
        out = m.group(0)
    if slice_spec is not None:
        out = apply_slice(out, slice_spec)
    return out


def regex_replace(text, pattern, replacement: str) -> str:
    """Every match of `pattern` in `text` replaced by `replacement` (re.sub semantics - `\\1` group
    backrefs work; implicit IGNORECASE is baked into `pattern` by the parser). No match -> the text
    unchanged. A bad group reference in the replacement raises a located ExprError (fail-loud, like
    a bad format spec) - an unknown group NAME too (`\\g<x>`: Python raises IndexError there, not
    re.error - it escaped as a crash; C-025 refute round 9)."""
    try:
        return pattern.sub(replacement, s(text))
    except (re.error, IndexError) as e:
        raise ExprError(f"regex_replace: bad replacement {replacement!r}: {e}")


# --- bit addresses ------------------------------------------------------------------------------ #
_BIT_ADDRESS = re.compile(r"([A-Za-z]+)(\d+)\.([0-7])")


def nth_bit(first, n) -> str:
    """The n-th BIT address counting from `first` - n = 1 is `first` itself, 8 bits a byte, the area letter(s)
    kept: `nth_bit("M200.0", 9)` -> "M201.0" (a generated flag's address from a base + its 1-based index, with
    no arithmetic in the language). A blank `n` stays blank; a `first` that is no `<area><byte>.<bit>` address
    (blank too - a base never set) or an `n` that is no whole number >= 1 raises a located ExprError."""
    if n is None or s(n).strip() == "":
        return ""
    m = _BIT_ADDRESS.fullmatch(s(first).strip())
    if not m:
        raise ExprError(f"nth_bit: {s(first)!r} is no <area><byte>.<bit> address (e.g. M200.0)")
    try:
        k = float(s(n).strip())                  # "0001" (an index) and a literal 8 (a float) alike
    except ValueError:
        k = 0.5
    if not k.is_integer():
        raise ExprError(f"nth_bit: {s(n)!r} is no whole number")
    k = int(k)
    if k < 1:
        raise ExprError(f"nth_bit: n = {k} - the first bit is n = 1")
    at = int(m.group(2)) * 8 + int(m.group(3)) + k - 1
    return f"{m.group(1).upper()}{at // 8}.{at % 8}"


# --- render-time format spec coercion ----------------------------------------------------------- #
# Merge of identity._format_value (int via int(float(x))) + dbtemplate.format_field (the conversion sets).
# Integer conversions coerce via int(float(value)); float conversions via float(value). A BLANK value
# (None or "") stays blank (emit "", no coercion). Bad coercion -> located ExprError.
_INT_CONV = "dxXobcn"
_FLOAT_CONV = "eEfFgG%"


def format_spec(value, spec: str) -> str:
    """Apply a Python format `spec` to `value` with numeric coercion. A blank value -> "". Coercion:
    int-conversions (d/x/X/o/b/c/n) via int(float(value)); float-conversions (e/E/f/F/g/G/%) via
    float(value). No conversion char -> format(value, spec) as-is. Raise ExprError on a bad spec."""
    if value is None or value == "":
        return ""
    last = spec[-1:] if spec else ""
    try:
        if last and last in _INT_CONV:
            return format(int(float(value)) if not isinstance(value, int) else value, spec)
        if last and last in _FLOAT_CONV:
            return format(float(value), spec)
        return format(value, spec)
    except (ValueError, TypeError, OverflowError) as e:     # OverflowError: {$n:d} on 'inf' (refuter round 7)
        raise ExprError(f"bad format spec {spec!r} for value {value!r}: {e}")
