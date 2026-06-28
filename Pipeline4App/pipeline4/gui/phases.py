"""The PL4 phase registry - the SINGLE source of the phase-bar metadata (headers + chevron sub-step
dropdowns + the dependency-ordered Run-all). The sub-button set is transcribed from the OPERATOR ORACLE
`Pipeline3App/assets/ButtonsLayout.xlsx` (the canonical map of the pipeline), minus phase 200 (PL4 has
NO Fill phase yet - STEP 4 builds it; until then PL4 requires a pre-filled I/O List).

Human strings are i18n KEYS, not literals: a phase carries `name_key`, a sub-button `label_key`, both
resolved through `core/i18n.tr(key, lang)` at render time (so EN/IT is a first-class shipped feature, not
a polish item). The registry STRUCTURE (numbers/kinds/sections/handlers) stays here.

A sub-button is one of three KINDS:
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
    label_key: str               # i18n key (resolved via core.i18n.tr)
    kind: str = "action"         # "action" | "open" | "special"
    enabled: bool = True         # False -> greyed (a deferred/unported oracle button, kept visible)
    opens: str = ""              # for kind="open": the target key the App resolves (see App._open_target)


@dataclass(frozen=True)
class Phase:
    number: int                  # 0 = Run-all; else the phase number (100, 300, ...)
    name_key: str                # i18n key for the header label
    kind: str = "phase"          # "run" | "phase" (-> the ButtonsLayout fill colour)
    handler: str = ""            # the App method that runs it (whole phase or a sub via only=); "" = display
    subs: tuple = ()             # the chevron dropdown buttons, in oracle order
    requires: tuple = ()         # the phase numbers this depends on (informational; for Run-all ordering)


# Ascending by number (the bar renders in this order), Run-all first. Sub-buttons per the oracle
# ButtonsLayout.xlsx; deferred/unported ones are kept VISIBLE but enabled=False (greyed).
PHASES = (
    Phase(0, "pb_run_pipeline", kind="run"),
    Phase(100, "ph_validation", handler="_run_validation", requires=(300,), subs=(
        Sub(110, "pb_validate_iolist"),
        Sub(120, "pb_validate_ce"),
        Sub(130, "pb_xcheck_cem_iol"),
        Sub(140, "pb_xcheck_iol_cem"),
        Sub(150, "pb_validate_diag", enabled=False),                     # deferred (touches 300 parity)
        Sub(155, "pb_clean_iolist", kind="special", enabled=False),      # clean.py not ported
        Sub(156, "pb_clean_cematrix", kind="special", enabled=False),
        Sub(160, "pb_open_errmgmt", kind="open", opens="error_mgmt"),
        Sub(170, "pb_open_iolist", kind="open", opens="iolist"),
        Sub(180, "pb_open_ce", kind="open", opens="matrix"),
        Sub(190, "pb_open_val_logs", kind="open", opens="validation_logs"),
    )),
    Phase(200, "ph_fill", handler="_run_fill", subs=(
        Sub(210, "pb_fill_script_type"),                                 # CSV-rule classification (built)
        Sub(220, "pb_fill_index", enabled=False),                       # §7 index - built next
        Sub(230, "pb_fill_diag_cabinet", enabled=False),                # §8 diag cabinet - later
        Sub(240, "pb_fill_diag_bit", enabled=False),                    # §8 diag bit - later
        Sub(250, "pb_open_iolist", kind="open", opens="iolist"),
    )),
    Phase(300, "ph_staging", handler="_run_staging", subs=(
        Sub(310, "pb_stage_iolist"),                                     # stage_iolist: I/O List only (no C&E)
        Sub(320, "pb_stage_cematrix"),                                   # stage: I/O List + C&E (the full staging)
        Sub(330, "pb_open_io_database", kind="open", opens="database"),
    )),
    Phase(400, "ph_interfaces", handler="_run_interfaces", requires=(300, 520), subs=(
        Sub(410, "pb_gen_interfaces"),
        Sub(420, "pb_open_interfaces", kind="open", opens="interfaces"),
        Sub(430, "pb_gen_custom_iface", kind="special", enabled=False),  # GUI popup not built
    )),
    Phase(500, "ph_signals", handler="_run_data_blocks", requires=(300,), subs=(
        Sub(510, "pb_gen_io_tags"),
        Sub(520, "pb_gen_data_blocks"),
        Sub(530, "pb_open_io_tags", kind="open", opens="io_tags"),
        Sub(540, "pb_open_data_blocks", kind="open", opens="blocks_import"),
    )),
    Phase(600, "ph_diagnosis", handler="_run_diagnosis", requires=(300, 520), subs=(
        Sub(610, "pb_gen_diag_list"),
        Sub(620, "pb_gen_diag_swblocks"),
        Sub(630, "pb_open_diag_data", kind="open", opens="diaglist"),
        Sub(640, "pb_open_diag_config", kind="open", opens="diag_config"),
    )),
    Phase(700, "ph_hardware", handler="_run_hardware", requires=(300,), subs=(
        Sub(710, "pb_gen_stations"),
        Sub(720, "pb_gen_modules"),
        Sub(730, "pb_open_hardware", kind="open", opens="hardware"),
    )),
    Phase(800, "ph_software", handler="_run_software", requires=(300, 520), subs=(
        Sub(810, "pb_gen_shells", enabled=False),                        # editable shells deferred
        Sub(820, "pb_gen_blocks"),
        Sub(830, "pb_gen_instances"),
        Sub(840, "pb_open_builder_shells", kind="open", enabled=False, opens="blocks_creation"),
        Sub(850, "pb_open_blocks_folder", kind="open", opens="blocks_import"),
    )),
    Phase(900, "ph_reporting", handler="_run_reporting", requires=(300,), subs=(
        Sub(910, "pb_gen_cov_pipeline"),
        Sub(920, "pb_gen_cov_tia", enabled=False),                       # 920 deferred (pending OP4 export)
        Sub(930, "pb_open_reports", kind="open", opens="coverage"),
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
    # ph200 (Fill) is excluded from Run-all for now: only 210 (script_type) is built, so a Run-all fill
    # would write a PARTIAL doc. It runs as its own button. Re-add here once 220/230/240 land.
    head = [n for n in nums if n not in tail and n != 200]
    head.sort(key=lambda n: (n != 300, n))          # 300 first, then ascending
    return head + tail
