"""`render(template, ctx, scope, mode)` - interpolate `{expr}` holes in a template.

A template is literal text with `{expr}` / `{expr:spec}` holes; non-brace text is copied verbatim. A cell
with NO holes is returned VERBATIM (a sentinel like "<input required>" is never parsed). The three
missing-key modes (port of identity.interp / interp_keep + a strict mode):

  "empty"  - a missing field evaluates to "" (the engine's default $-ref behaviour)
  "keep"   - a hole whose TOP-LEVEL field is not in ctx is left as the literal {token}; a present-but-empty
             field substitutes to "" (interp_keep semantics)
  "strict" - a missing field raises ExprError

The format-spec (`{expr:spec}`) coercion lives in runtime.format_spec (blank stays blank).
"""
from __future__ import annotations

import re

from .errors import ExprError
from .parser import referenced_fields
from .runtime import format_spec, s
from .scope import Scope

# A hole = {  <expr>  [ : <spec> ] }  - we split on the LAST top-level ':' so a regex inside the expr
# (which can't contain a bare ':' outside a string here) doesn't confuse the spec. The expr part is
# compiled by the engine; the spec part is a Python format spec.
_HOLE = re.compile(r"\{([^{}]*)\}")


def _split_spec(body: str):
    """Split a hole body into (expr_text, spec_or_None). The spec is the tail after the LAST top-level
    ':' - one not inside a quoted string, a /regex/, or any (...)/[...] (so a slice like `-1:` inside an
    extract(...) call, or a `:` inside a string, is NOT mistaken for the format spec)."""
    depth_str = depth_re = False
    depth = 0
    last_colon = -1
    i = 0
    while i < len(body):
        c = body[i]
        if depth_str:
            if c == "\\":
                i += 2
                continue
            if c == '"':
                depth_str = False
        elif depth_re:
            if c == "\\":
                i += 2
                continue
            if c == "/":
                depth_re = False
        else:
            if c == '"':
                depth_str = True
            elif c == "/":
                depth_re = True
            elif c in "([":
                depth += 1
            elif c in ")]":
                depth -= 1
            elif c == ":" and depth == 0:
                last_colon = i
        i += 1
    if last_colon < 0:
        return body, None
    return body[:last_colon], body[last_colon + 1:]


def render(template: str, ctx: dict, scope: Scope | None = None, mode: str = "empty") -> str:
    """Interpolate `{expr}` holes in `template` against `ctx`. `mode` in {empty, keep, strict}."""
    if mode not in ("empty", "keep", "strict"):
        raise ExprError(f"render: unknown mode {mode!r} (use empty|keep|strict)")
    from . import _compile                                  # late import (avoid a cycle with __init__)

    def sub(m):
        body = m.group(1)
        if not body.strip():
            return ""                                       # {} or { } -> ""

        expr_text, spec = _split_spec(body)
        # keep / strict: decide missing-ness over EVERY top-level $field in the hole (incl. ones nested in
        # function-call args), not just a bare `$field` hole - so a missing field in {concat($x)} is caught.
        if mode in ("keep", "strict"):
            missing = [f for f in referenced_fields(expr_text) if f not in ctx]
            if missing:
                if mode == "keep":
                    return m.group(0)                       # leave {token} intact
                raise ExprError(f"render(strict): missing field ${missing[0]} in {template!r}")

        value = _compile(expr_text.strip(), scope)(ctx)
        if spec is not None:
            return format_spec(value, spec)
        return s(value)

    return _HOLE.sub(sub, template or "")
