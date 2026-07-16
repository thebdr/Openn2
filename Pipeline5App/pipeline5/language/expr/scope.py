"""`Scope` - the compile-time set of valid top-level `$names`.

A Scope is a frozen set of the field names a `$ref` is allowed to use. At COMPILE the parser looks up
each top-level `$x` in the active scope; an unknown name raises a located `ExprError`. `scope=None`
(no Scope) means permissive - any `$name` is allowed and a missing field evaluates to "" (never throws).

`let(...)` extends the scope for the duration of a binding's body: a `with_names(extra)` returns a NEW
Scope carrying the original names plus the let-bound ones, so the body may reference them while the
outer compile context stays unchanged. Scope identity (NOT contents) participates in the compiled-expr
cache key, so two equal-but-distinct Scopes compile independently (cheap + correct).
"""
from __future__ import annotations


class Scope:
    """The set of valid top-level `$names`. Immutable; `with_names` returns an extended copy."""

    __slots__ = ("names",)

    def __init__(self, names=()):
        self.names = frozenset(names)

    def __contains__(self, name) -> bool:
        return name in self.names

    def with_names(self, extra) -> "Scope":
        """A new Scope carrying these names plus `extra` (used to admit let-bound names in a body)."""
        return Scope(self.names | frozenset(extra))

    def __repr__(self) -> str:
        return f"Scope({sorted(self.names)!r})"
