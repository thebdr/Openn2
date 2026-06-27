"""The builder registry: a builder self-registers via the `@builds("<name>")` decorator (verbatim port
of PL3's `domain/blocks/registry.py`).

`<name>` is the OUTPUT block name (the template stem with the `TEMPLATE--vX.Y--` prefix dropped, e.g.
"06_Feedback Error"). The engine runs every registered builder over the Database.
"""
from __future__ import annotations

_REGISTRY: dict = {}


def builds(name: str):
    """Register a builder for output block `name`. The decorated function takes a Database and returns a
    Table."""
    def deco(fn):
        _REGISTRY[name] = fn
        return fn
    return deco


def registry() -> dict:
    """{name: builder_fn} for every registered builder (a copy)."""
    return dict(_REGISTRY)


def clear() -> None:
    """Test helper: drop all registrations."""
    _REGISTRY.clear()
