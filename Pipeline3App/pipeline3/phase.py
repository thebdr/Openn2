"""The Phase abstraction (plan §4).

A Phase is a frozen descriptor: its number (100..900), stable key, i18n label, the phase numbers
it `requires` (the DAG edges), a `run(ctx)->PhaseResult`, the dropdown `buttons`, optional
`sub_phases` (validation 110-150; fill 210-240), and documentation of inputs/outputs. The numbers
live here - the registry IS the enumeration, so there is no second ordered list to keep in sync.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Optional, Sequence

# Button kinds -> theme styles (white/blue/orange/grey); see theme.button_styles.
KIND_ACTION = "action"      # white - a generation/run step
KIND_OPEN = "open"          # light blue - open a file/folder
KIND_SPECIAL = "special"    # orange - special action (e.g. a popup)
KIND_DISABLED = "disabled"  # greyed stub


@dataclass(frozen=True)
class PhaseResult:
    """What a phase.run returns. `log` are LogEntry objects; `artifacts` maps an OUTPUT_PATHS key
    to the path actually written. `halt=True` stops the orchestrator (e.g. unresolved populate)."""
    ok: bool = True
    halt: bool = False
    log: Sequence = field(default_factory=list)
    artifacts: dict = field(default_factory=dict)
    summary: str = ""


@dataclass(frozen=True)
class Button:
    """One dropdown button. `kind` drives color. `command_key` is what the GUI/CLI binds:
    for an action it is usually the (sub-)phase number to run; for an open it is an OUTPUT_PATHS
    key or a project-doc key."""
    label_key: str
    kind: str = KIND_ACTION
    number: Optional[int] = None      # slot-derived number for action steps (e.g. 110); None for opens
    command_key: str = ""


@dataclass(frozen=True)
class SubPhase:
    """A numbered step inside a phase (validation 110-150; fill 210-240). `run` may be None for a
    not-yet-implemented stub (rendered disabled)."""
    number: int
    key: str
    name_key: str
    run: Optional[Callable] = None


@dataclass(frozen=True)
class Phase:
    number: int                       # 100..900 (hundreds)
    key: str                          # stable slug, e.g. "validation"
    name_key: str                     # i18n header label key, e.g. "ph_validation"
    run: Callable                     # (ctx) -> PhaseResult; runs the whole phase
    requires: Sequence = ()           # phase numbers this phase depends on (DAG edges)
    buttons: Sequence = ()            # Button specs for the chevron dropdown
    sub_phases: Sequence = ()         # SubPhase list
    inputs: Sequence = ()             # doc/config keys read (documentation only)
    outputs: Sequence = ()            # OUTPUT_PATHS keys written (documentation only)
