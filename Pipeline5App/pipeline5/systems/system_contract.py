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
class Sub:
    """One chevron-dropdown sub-button of a phase (transcribed per system from its operator oracle -
    Siemens: `Pipeline3App/assets/ButtonsLayout.xlsx`). Three KINDS:
      * action  - run that sub-phase: the phase handler is invoked with `only=<number>`
      * open    - open a folder/file: `opens` names the target the GUI resolves to a path
                  (System.open_targets first, then System.output_layout, then the kernel targets)
      * special - a standalone handler of its own: `opens` names the System.handlers key
    `enabled=False` renders the button GREYED (a deferred/unported step kept VISIBLE for oracle
    fidelity)."""
    number: int                  # phase + slot (110, 320, ...) - the oracle id
    label_key: str               # i18n key (resolved via language.i18n.tr)
    kind: str = "action"         # "action" | "open" | "special"
    enabled: bool = True         # False -> greyed (a deferred/unported oracle button, kept visible)
    opens: str = ""              # open: the GUI open-target key | special: the System.handlers key


@dataclass(frozen=True)
class Phase:
    """One phase-bar button + its dropdown. `handler` is a System.handlers KEY (not a callable, not
    an App method name - the same registry row works for any host that carries the system's handler
    dict); "" = a display-only phase. Human strings are i18n KEYS resolved at render time."""
    number: int                  # 0 = Run-all; else the phase number (100, 300, ...)
    name_key: str                # i18n key for the header label
    kind: str = "phase"          # "run" | "phase" (-> the oracle fill colour)
    handler: str = ""            # System.handlers key running it (whole phase or only=<sub>); "" = display
    subs: tuple = ()             # the chevron dropdown buttons, in oracle order
    requires: tuple = ()         # the phase numbers this depends on (informational)


@dataclass(frozen=True)
class PhaseSet:
    """A system's WHOLE phase registry - what the phase bar renders and Run-all executes (PL4
    coupling #9: the GUI projection is per system, dispatched through System.handlers).

    `run_plan` is EXPLICIT data, not a derivation: the phase numbers Run-all executes, in order.
    Adding a phase means deciding its Run-all position (or deliberately leaving it out - Siemens
    keeps 200 Fill manual because it mutates the source document). Validated at construction:
    every plan entry must name a runnable phase, every number must be unique - a typo fails at
    system import, not at the button click."""
    phases: tuple                # Phase rows, bar order (Run-all first)
    run_plan: tuple = ()         # the Run-all phase numbers, execution order (explicit, validated)

    def __post_init__(self):
        numbers = [p.number for p in self.phases]
        if len(numbers) != len(set(numbers)):
            raise ValueError("PhaseSet: duplicate phase numbers")
        subs = [s.number for p in self.phases for s in p.subs]
        if len(subs) != len(set(subs)):
            raise ValueError("PhaseSet: duplicate sub-button numbers")
        runnable = {p.number for p in self.phases if p.handler}
        bad = [n for n in self.run_plan if n not in runnable]
        if bad:
            raise ValueError(f"PhaseSet: run_plan names non-runnable phases {bad}")
        if len(self.run_plan) != len(set(self.run_plan)):
            raise ValueError("PhaseSet: duplicate run_plan entries")

    def __iter__(self):
        return iter(self.phases)

    def runnable(self) -> tuple:
        """The phases with a real handler, in registry order."""
        return tuple(p for p in self.phases if p.handler)

    def by_number(self, number: int):
        return next((p for p in self.phases if p.number == number), None)

    def phase_of_sub(self, sub_number: int):
        """The parent phase owning a sub-button number (a sub click dispatches to `handler(only=…)`)."""
        return next((p for p in self.phases for s in p.subs if s.number == sub_number), None)

    def sub_by_number(self, sub_number: int):
        for phase in self.phases:
            for sub in phase.subs:
                if sub.number == sub_number:
                    return sub
        return None

    def run_order(self) -> list:
        """The Run-all execution order - the explicit `run_plan`, as a fresh list."""
        return list(self.run_plan)


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
    """What the host hands a system's phase handler (the step-5 seam).

    Handlers live in the system's `main.py` as `def run_x(ctx, only=None)` - they are NOT App
    methods and never touch Tk: everything host-side (the log, the status bar, the halt flag)
    goes through these callables. That makes every handler runnable HEADLESS - the phase-button
    smoke test drives them with plain-function seams against the real fixture documents.
    """
    system: "System"
    emit: object = None      # callable(level, text) -> None: the structured log line
    status: object = None    # callable(text) -> None: the status bar
    gate: object = None      # callable(findings, label=…) -> bool: apply treatments + render; False = halt
    render: object = None    # callable(findings, label=…) -> None: render-only (pure projections)
    records: object = None   # callable(records) -> None: post PRE-RENDERED structured log records
    halt: object = None      # callable() -> None: mark the RUN halted (Run-all stops the chain)
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
    phases: object = None                # PhaseSet - the system's phase bar + Run-all plan (coupling #9)
    handlers: dict = field(default_factory=dict)       # {Phase.handler key: callable(ctx, only=None)}
    open_targets: dict = field(default_factory=dict)   # {opens-key: path_fn} - resolved FIRST, before
                                         # output_layout.dirs() and the host's kernel targets
    symbols: SymbolFormatter = None      # the system's symbol notation (coupling #1)
    emitters: dict = field(default_factory=dict)       # {emit_kind: writer_fn} (coupling #2)
    builders: BuilderRegistry = field(default_factory=BuilderRegistry)
    templates: object = None             # the block-template inventory (template_keys/stem_ref_by_name/
                                         # template_ref) the 800 engine reads - system truth, not kernel
    output_layout: OutputLayout = None   # the delivery tree (coupling #3)
    config_root: str = ""                # the system's BUILTIN config_project dir (4-tier resolver, tier 3)

    def __post_init__(self):
        if not self.id or not str(self.id).strip():
            raise ValueError("System.id must be a non-empty string")
        if not self.taxonomy:
            raise ValueError(f"System {self.id!r}: taxonomy must name the display tree")
