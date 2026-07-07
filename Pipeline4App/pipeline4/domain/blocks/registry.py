"""The builder registry: a builder self-registers via the `@builds("<name>")` decorator (port of PL3's
`domain/blocks/registry.py`, extended with the emit-kind declaration - UI_REFRESH_PLAN F).

`<name>` is the OUTPUT block name (the template stem with the `TEMPLATE--vX.Y--` prefix dropped, e.g.
"06_Feedback Error"). The engine runs every registered builder over the Database.

`emit` declares the block's OUTPUT SURFACE - the property lives WITH the builder (the user-coded
custom section) instead of a hardcoded name-set in the engine:
  * "csv"    - the default $/#/%/@ CreationInfo CSV (template-fill via OP4)
  * "fc_xml" - a ready SW.Blocks.FC XML emitted to ImportReady; the CreationInfo CSV is dropped
  * "scl"    - a ready SCL FUNCTION source (scl_emit) emitted to ImportReady; no CSV either
"""
from __future__ import annotations

_REGISTRY: dict = {}
_EMIT: dict = {}


def builds(name: str, emit: str = "csv"):
    """Register a builder for output block `name` (+ its declared output surface). The decorated
    function takes a Database and returns a Table."""
    def deco(fn):
        _REGISTRY[name] = fn
        _EMIT[name] = emit
        return fn
    return deco


def registry() -> dict:
    """{name: builder_fn} for every registered builder (a copy)."""
    return dict(_REGISTRY)


def emit_kind(name: str) -> str:
    """The declared output surface for block `name` ("csv" when unregistered/undeclared)."""
    return _EMIT.get(name, "csv")


def clear() -> None:
    """Test helper: drop all registrations."""
    _REGISTRY.clear()
    _EMIT.clear()
