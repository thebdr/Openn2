"""The located error type for the unified expression engine.

`ExprError` is the single failure type the whole package raises - a malformed expression, an unknown
top-level $field under a Scope, a bad format spec, a strict-mode missing render key. Like rule_expr's
`RuleError` it is a `ValueError` subclass and carries the source text in its message (fail-loud, located).
"""
from __future__ import annotations


class ExprError(ValueError):
    """A malformed / invalid expression or template (located message - includes the source text)."""
