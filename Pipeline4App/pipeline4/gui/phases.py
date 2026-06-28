"""The PL4 phase registry - the SINGLE source of the phase-bar metadata (headers + chevron sub-step
dropdowns + the dependency-ordered Run-all). The sub-button set is transcribed from the OPERATOR ORACLE
`Pipeline3App/assets/ButtonsLayout.xlsx` (the canonical map of the pipeline), minus phase 200 (PL4 has
NO Fill phase - it reads the source documents fresh every run, DESIGN 10.6).

Each phase carries its sub-buttons in oracle order. A sub-button is one of three KINDS:
  * action  - run that sub-phase (its prerequisites are built first by the phase handler)
  * open    - open a folder/file (`opens` names the target the App resolves to a path)
  * special - a GUI-only action (e.g. the Clean popups) - PL4 has none yet
`enabled=False` renders the button GREYED (a deferred/unported step kept VISIBLE for oracle fidelity).
A phase `handler` runs the whole phase (`only=None`) or one sub-phase (`only=<number>`); the App dispatch
maps an action sub-button -> `handler(only=number)`.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Sub:
    number: int                  # phase + slot (110, 320, ...) - the ButtonsLayout id
    title: str
    kind: str = "action"         # "action" | "open" | "special"
    enabled: bool = True         # False -> greyed (a deferred/unported oracle button, kept visible)
    opens: str = ""              # for kind="open": the target key the App resolves (see App._open_target)


@dataclass(frozen=True)
class Phase:
    number: int                  # 0 = Run-all; else the phase number (100, 300, ...)
    title: str
    kind: str = "phase"          # "run" | "phase" (-> the ButtonsLayout fill colour)
    handler: str = ""            # the App method that runs it (whole phase or a sub via only=); "" = display
    subs: tuple = ()             # the chevron dropdown buttons, in oracle order
    requires: tuple = ()         # the phase numbers this depends on (informational; for Run-all ordering)


# Ascending by number (the bar renders in this order), Run-all first. Sub-buttons per the oracle
# ButtonsLayout.xlsx; deferred/unported ones are kept VISIBLE but enabled=False (greyed).
PHASES = (
    Phase(0, "Run Pipeline", kind="run"),
    Phase(100, "Documents Validation", handler="_run_validation", requires=(300,), subs=(
        Sub(110, "Validate I/O List"),
        Sub(120, "Validate C&E Matrix"),
        Sub(130, "Cross-Check CEM->IOL"),
        Sub(140, "Cross-Check IOL->CEM"),
        Sub(150, "Validate Diagnosis Assignments", enabled=False),       # deferred (touches 300 parity)
        Sub(155, "Clean IOList Addresses & FLD", kind="special", enabled=False),  # clean.py not ported
        Sub(156, "Clean CEMatrix Addresses & FLD", kind="special", enabled=False),
        Sub(160, "Open Error Management .csv", kind="open", opens="error_mgmt"),
        Sub(170, "Open I/O List", kind="open", opens="iolist"),
        Sub(180, "Open Cause&Effect Matrix", kind="open", opens="matrix"),
        Sub(190, "Validation Logs Folder", kind="open", opens="validation_logs"),
    )),
    Phase(300, "Documents Staging", handler="_run_staging", subs=(
        Sub(310, "Stage I/O List"),
        Sub(320, "Stage C&E Matrix", enabled=False),                     # PL4: stage() reads the I/O List + enriches from the C&E in one pass
        Sub(330, "Open IO Database", kind="open", opens="database"),
    )),
    Phase(400, "Interfaces Generation", handler="_run_interfaces", requires=(300, 520), subs=(
        Sub(410, "Generate Interfaces"),
        Sub(420, "Open Interfaces Folder", kind="open", opens="interfaces"),
        Sub(430, "Generate Custom Interface …", kind="special", enabled=False),   # GUI popup not built
    )),
    Phase(500, "Signals Mapping", handler="_run_data_blocks", requires=(300,), subs=(
        Sub(510, "Generate I/O Tags"),
        Sub(520, "Generate Data Blocks"),
        Sub(530, "Open IO Tags", kind="open", opens="io_tags"),
        Sub(540, "Open Data Blocks Folder", kind="open", opens="blocks_import"),
    )),
    Phase(600, "Diagnosis Mapping", handler="_run_diagnosis", requires=(300, 520), subs=(
        Sub(610, "Generate Diag List"),
        Sub(620, "Generate Diag Software Blocks"),
        Sub(630, "Open Diag Data Folder", kind="open", opens="diaglist"),
        Sub(640, "Open Diag Config .csv Folder", kind="open", opens="diag_config"),
    )),
    Phase(700, "Hardware Generation", handler="_run_hardware", requires=(300,), subs=(
        Sub(710, "Generate Stations"),
        Sub(720, "Generate Modules"),
        Sub(730, "Open Hardware Data Folder", kind="open", opens="hardware"),
    )),
    Phase(800, "Software Generation", handler="_run_software", requires=(300, 520), subs=(
        Sub(810, "Generate Empty Shells .xlsm", enabled=False),          # editable shells deferred
        Sub(820, "Generate Blocks"),
        Sub(830, "Generate Instances"),
        Sub(840, "Open Builder Shells .xlsm", kind="open", enabled=False, opens="blocks_creation"),
        Sub(850, "Open Generated Blocks Folder", kind="open", opens="blocks_import"),
    )),
    Phase(900, "Reporting", handler="_run_reporting", requires=(300,), subs=(
        Sub(910, "Generate Pipeline Coverage Report"),
        Sub(920, "Generate TIA Project Coverage Report", enabled=False),  # 920 deferred (pending OP4 export)
        Sub(930, "Open Reports Folder", kind="open", opens="coverage"),
    )),
)

# The phases with a real handler (runnable), in registry order.
RUNNABLE = tuple(p for p in PHASES if p.handler)


def by_number(number: int) -> Phase | None:
    return next((p for p in PHASES if p.number == number), None)


def phase_of_sub(sub_number: int) -> Phase | None:
    """The parent phase owning a sub-button number (so the App dispatches a sub to `handler(only=…)`)."""
    return next((p for p in PHASES for s in p.subs if s.number == sub_number), None)


def sub_by_number(sub_number: int) -> Sub | None:
    for phase in PHASES:
        for sub in phase.subs:
            if sub.number == sub_number:
                return sub
    return None


def run_order() -> list:
    """The phase numbers to run for Run-all, in a sensible dependency order: staging (300) first, then the
    builders, then Reporting (900, reads every build) and Validation (100). Each PL4 handler is
    self-contained (re-stages its own prerequisites), so order drives the log narrative, not correctness."""
    nums = [p.number for p in RUNNABLE]
    tail = [n for n in (900, 100) if n in nums]
    head = [n for n in nums if n not in tail]
    head.sort(key=lambda n: (n != 300, n))          # 300 first, then ascending
    return head + tail
