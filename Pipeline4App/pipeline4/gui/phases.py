"""The lightweight PL4 phase registry - the SINGLE source of the phase metadata the GUI consumes (the
phase-button bar, the chevron sub-phases, and the dependency-ordered Run-all), so the phase order/labels
are not re-encoded in two places (the bug PL3's registry was built to avoid). GUI-scoped for now; if a CLI
or engine lands it can move to core.

PL4 has NO Fill phase (200) - it reads the source documents fresh every run (DESIGN 10.6), so 200 is absent.
`handler` is the `App` method name that runs the phase; a phase with no handler is display-only.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Phase:
    number: int                  # 0 = the Run-all action; else the phase number (100, 300, ...)
    title: str
    kind: str = "phase"          # "run" | "phase" (-> the ButtonsLayout fill colour)
    handler: str = ""            # the App method that runs it ("" = display-only)
    subs: tuple = ()             # ((number, label), ...) the sub-phase steps (the M4 chevron dropdown)
    requires: tuple = ()         # the phase numbers this depends on (informational; for Run-all ordering)


# Ascending by number (the bar renders in this order), Run-all first. PL4's real phases only.
PHASES = (
    Phase(0, "Run Pipeline", kind="run"),
    Phase(100, "Documents Validation", handler="_run_validation",
          subs=((110, "Validate I/O List"), (120, "Validate C&E Matrix"),
                (130, "Cross-Check CEM->IOL"), (140, "Cross-Check IOL->CEM")), requires=(300,)),
    Phase(300, "Documents Staging", handler="_run_staging", subs=((310, "Stage I/O List"),)),
    Phase(400, "Interfaces Generation", handler="_run_interfaces",
          subs=((400, "Build Interfaces"),), requires=(300, 520)),
    Phase(500, "Signals Mapping", handler="_run_data_blocks",
          subs=((520, "Data Blocks"), (510, "I/O Tags")), requires=(300,)),
    Phase(600, "Diagnosis Mapping", handler="_run_diagnosis",
          subs=((610, "DiagList"), (620, "OPC SCL")), requires=(300, 520)),
    Phase(700, "Hardware Generation", handler="_run_hardware",
          subs=((710, "Stations"), (720, "Modules")), requires=(300,)),
    Phase(800, "Software Generation", handler="_run_software",
          subs=((820, "Blocks"), (830, "Instances")), requires=(300, 520)),
    Phase(900, "Reporting", handler="_run_reporting", subs=((910, "Pipeline Coverage"),), requires=(300,)),
)

# The phases with a real handler (runnable), in registry order.
RUNNABLE = tuple(p for p in PHASES if p.handler)


def by_number(number: int) -> Phase | None:
    return next((p for p in PHASES if p.number == number), None)


def run_order() -> list:
    """The phase numbers to run for Run-all, in a sensible dependency order: staging (300) first, then the
    builders, then Reporting (900, reads every build) and Validation (100). Each PL4 handler is
    self-contained (re-stages its own prerequisites), so order drives the log narrative, not correctness."""
    nums = [p.number for p in RUNNABLE]
    tail = [n for n in (900, 100) if n in nums]
    head = [n for n in nums if n not in tail]
    head.sort(key=lambda n: (n != 300, n))          # 300 first, then ascending
    return head + tail
