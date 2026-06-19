"""Phase 100 - Documents Validation. The 5 sub-phases (110-150) validate the hand-authored I/O
List + Cause & Effect matrix and write two reports (complete + error-only). Depends on Staging
(300) - it reads ctx.rows for 130/140/150 and the workbooks (via io.workbook) for 110/120.

The treatment registry (warn/skip/accept) is a later milestone; this phase only guarantees every
[FAIL] line carries a stable LogEntry.uid for that registry to key on.

Profiles: `main` runs all five; `designer` (validation-only: 300 read-only stage -> 100) runs
110-140 - 150 (diagnosis) is disabled because its inputs come from Fill (200), which the designer
build never runs, so the designer GUI greys the 150 button.
"""
from __future__ import annotations
import os

from pipeline3.phase import Phase, SubPhase, PhaseResult, Button, KIND_ACTION, KIND_OPEN
from pipeline3.registry import register, registry
from pipeline3.core import config
from pipeline3.core.i18n import tr
from pipeline3.core.model import banner
from pipeline3.io import render
from pipeline3.domain import validation

# (number, button/i18n label key, builder, enabled-in-designer)
SUBS = (
    (110, "pb_validate_iolist", validation.run_iolist,        True),
    (120, "pb_validate_ce",     validation.run_ce_matrix,     True),
    (130, "pb_xcheck_cem_iol",  validation.run_xcheck_cem_iol, True),
    (140, "pb_xcheck_iol_cem",  validation.run_xcheck_iol_cem, True),
    (150, "pb_validate_diag",   validation.run_diagnosis,     False),
)


def _write(out_root: str, key: str, text: str) -> str:
    path = config.out_path(out_root, key) + ".txt"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def _run_sub(ctx, number, name_key, builder, designer_ok):
    """One sub-phase, self-contained (its prerequisites are topo-run by app.run_phase)."""
    if ctx.profile == "designer" and not designer_ok:
        return PhaseResult(ok=True, summary=f"{number}: disabled in the designer profile")
    log = [banner(number, tr(name_key, ctx.lang))] + list(builder(ctx))
    fails = sum(e.level == "FAIL" for e in log)
    return PhaseResult(ok=(fails == 0), log=log, summary=f"{number}: {fails} FAIL")


def run(ctx) -> PhaseResult:
    """Phase header: run every (profile-enabled) sub-phase, write both reports."""
    log = [banner(100, tr("ph_validation", ctx.lang))]
    for number, name_key, builder, designer_ok in SUBS:
        if ctx.profile == "designer" and not designer_ok:
            continue
        log.append(banner(number, tr(name_key, ctx.lang)))
        log.extend(builder(ctx))
    bodies = render.reports(log)
    rep = _write(ctx.out_root, "validation_report", bodies["complete"])
    err = _write(ctx.out_root, "validation_errors", bodies["errors"])
    fails = sum(e.level == "FAIL" for e in log)
    ctx.emit(f"validation: {fails} FAIL -> {os.path.basename(rep)} / {os.path.basename(err)}")
    return PhaseResult(ok=(fails == 0), halt=False, log=log,
                       artifacts={"validation_report": rep, "validation_errors": err},
                       summary=f"{fails} FAIL, 2 reports written")


SUB_PHASES = [
    SubPhase(n, key.replace("pb_", ""), key,
             (lambda c, n=n, key=key, b=b, d=d: _run_sub(c, n, key, b, d)))
    for (n, key, b, d) in SUBS
]

BUTTONS = [
    Button("pb_validate_iolist", KIND_ACTION, 110, "110"),
    Button("pb_validate_ce", KIND_ACTION, 120, "120"),
    Button("pb_xcheck_cem_iol", KIND_ACTION, 130, "130"),
    Button("pb_xcheck_iol_cem", KIND_ACTION, 140, "140"),
    Button("pb_validate_diag", KIND_ACTION, 150, "150"),
    Button("pb_open_iolist", KIND_OPEN, 160, "open:io_list"),
    Button("pb_open_ce", KIND_OPEN, 170, "open:ce"),
    Button("pb_open_val_logs", KIND_OPEN, 180, "open:validation_report"),
]

register(Phase(
    number=100, key="validation", name_key="ph_validation", run=run, requires=(300,),
    buttons=BUTTONS, sub_phases=SUB_PHASES,
    inputs=("io_list.path", "ce.path", "signal_types.csv", "column_map.csv",
            "iolist_permanent_parts.csv"),
    outputs=("validation_report", "validation_errors"),
))

# Designer profile = validation-only: 300 read-only stage -> 100 (sub-phases 110-140).
registry().define_profile("designer", (300, 100))
