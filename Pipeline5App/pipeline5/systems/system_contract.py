"""The system-type plugin contract - what a target system IS to the kernel.

Each supported controller system (Siemens S7 Safety, the Intervalzero RTX trio, ...) lives in its
own package under `pipeline5/systems/<platform>/<toolchain>/<system>/` and exposes ONE module-level
`SYSTEM = System(...)` descriptor from its `system.py`. The descriptor carries every point where
behaviour differs per system, so shared kernel code takes a `System` parameter and NEVER branches
on a type id (the grep-gate test enforces this).

Registration is EXPLICIT: `pipeline5/systems/catalog.py` imports each system.py and lists
`ALL_SYSTEMS` - no directory scanning, no entry points; a missing/typo'd system fails loudly at
import (PL5 plan, risk #5: strict dependency direction - the kernel never imports systems/*;
catalog.py is the single composition point, consumed only by the GUI/project layers).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SystemCapabilities:
    """What shared pipeline stages this system needs - shared code gates on these FLAGS, never on
    the system id. Extended only when a REAL second consumer appears (plan risk #3)."""
    needs_ce_matrix: bool = False          # gates the 320 C&E-annotation leg + C&E validation
    needs_diagnosis_blocks: bool = False   # gates the DiagnosisBlocks sheet staging + its checks


class SymbolFormatter:
    """How this system spells a symbol reference (PL4 coupling #1: the TIA-quoted plc_binding).

    The kernel stores whatever `binding()` returns in the SSOT (`plc_binding` column - the column
    name survives; it means 'the system's symbol reference'). Systems subclass with their notation:
    Siemens -> '"<db>"."<member>"', RTX -> its own (spec'd with the RTX toolchain).
    """

    def binding(self, db: str, member: str) -> str:
        raise NotImplementedError

    def quote(self, name: str) -> str:
        raise NotImplementedError

    def parse_binding(self, text: str):
        """The inverse of binding() -> (db, member), or None if `text` is not a binding."""
        raise NotImplementedError


class OutputLayout:
    """The system's DELIVERY tree under the project output root (PL4 coupling #3).

    The kernel keeps only the neutral dirs (Database/, ProjectDocumentation/, Reports/); every
    delivery dir (Siemens: TiaPortalProjectInterface/BuilderData/...) is asked of the system's own
    layout by the system's own handlers. `dirs()` maps a stable key (also the GUI open-target key)
    -> absolute dir path for the CURRENT project/output root.
    """

    def dirs(self) -> dict:
        raise NotImplementedError


class BuilderRegistry:
    """Instance-based port of PL4 `domain/blocks/registry.py` - one registry PER SYSTEM.

    The module-global `_REGISTRY` died with PL4: two systems must not see each other's builders.
    A builder self-registers via the `@SYSTEM.builders.builds("<name>", emit=...)` decorator; `emit`
    declares the block's OUTPUT SURFACE and is resolved through `System.emitters` (coupling #2 -
    unknown kind raises there, never a silent default writer).
    """

    def __init__(self) -> None:
        self._registry: dict = {}
        self._emit: dict = {}

    def builds(self, name: str, emit: str = "csv"):
        """Register a builder for output block `name` (+ its declared output surface). The
        decorated function takes a Database and returns a Table."""
        def deco(fn):
            self._registry[name] = fn
            self._emit[name] = emit
            return fn
        return deco

    def registry(self) -> dict:
        """{name: builder_fn} for every registered builder (a copy)."""
        return dict(self._registry)

    def emit_kind(self, name: str) -> str:
        """The declared output surface for block `name` ("csv" when undeclared)."""
        return self._emit.get(name, "csv")

    def clear(self) -> None:
        """Test helper: drop all registrations."""
        self._registry.clear()
        self._emit.clear()


@dataclass
class PhaseContext:
    """What the GUI hands a system's phase handler (wired at migration step 5).

    Handlers live in the system's `main.py` as `def run_x(ctx, only=None)` - they stop being App
    methods. The context carries the log/gate seams so a handler never touches Tk directly.
    """
    system: "System"
    emit: object = None      # callable(level, text) -> None: the structured log line
    status: object = None    # callable(text) -> None: the status bar
    gate: object = None      # callable(findings, label) -> bool: apply treatments + render + halt on FAIL
    render: object = None    # callable(findings, label) -> None: render-only (pure projections)
    lang: str = "en"


@dataclass(frozen=True)
class System:
    """One target system - the whole plugin contract in one immutable descriptor.

    Shallow-frozen: the dict/registry members are mutated only during the system package's own
    import (builders registering themselves), never by the kernel.
    """
    id: str                              # persisted in project meta; surfaces in Database/<id>, config_project/systems/<id>
    name_key: str                        # i18n key for the display name
    taxonomy: tuple                      # display tree, e.g. ("PLC_Based", "SiemensS7", "Safety")
    capabilities: SystemCapabilities = field(default_factory=SystemCapabilities)
    phases: object = None                # PhaseSet (gui/phase_model.py, lands at step 5)
    handlers: dict = field(default_factory=dict)       # {Phase.handler key: callable(ctx, only=None)}
    open_targets: dict = field(default_factory=dict)   # {opens-key: path_fn}, merged over kernel targets
    symbols: SymbolFormatter = None      # the system's symbol notation (coupling #1)
    emitters: dict = field(default_factory=dict)       # {emit_kind: writer_fn} (coupling #2)
    builders: BuilderRegistry = field(default_factory=BuilderRegistry)
    output_layout: OutputLayout = None   # the delivery tree (coupling #3)
    config_root: str = ""                # the system's BUILTIN config_project dir (4-tier resolver, tier 3)

    def __post_init__(self):
        if not self.id or not str(self.id).strip():
            raise ValueError("System.id must be a non-empty string")
        if not self.taxonomy:
            raise ValueError(f"System {self.id!r}: taxonomy must name the display tree")
