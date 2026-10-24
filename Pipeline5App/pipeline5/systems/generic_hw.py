"""The GENERIC HARDWARE systems' shared chapters (user 2026-10-24: "generic hardware (Siemens Tia Portal),
generic hardware (Hilscher Sycon.Net) (only validation + hardware generation enabled)"): a project of one of
these types holds an I/O List whose PROFINET nodes are to be built as a hardware configuration - no program,
no blocks, no C&E. Two phases, both runnable headless through the PhaseContext seams:

  100 Validation  - the I/O List checks only (110): the document's own rules plus the per-type mandatory
                    columns (`column_map.csv` `mandatory_in`: a node row must fill name, model and IP) and
                    the duplicate PROFINET name / IP checks; the report written like the Siemens 100
  700 Hardware    - TIA:   the siemens_s7 hardware build + the hw/* BuilderData export (the OP5 workspace);
                    SYCON: the hw/sycon-* handoff (`sycon_handoff.project`) into `<output root>/
                    SyconNetProjectInterface` (what Sycon5App consumes)

Both systems import this module (systems may import systems - law L3 binds the kernel, not the plugins).
"""
from __future__ import annotations

import os

from pipeline5.language import i18n
from pipeline5.systems.system_contract import OutputLayout, Phase, PhaseSet, Sub


# --------------------------------------------------------------------------------------------- #
# The phase registries - validation and hardware only (the point of these types)
# --------------------------------------------------------------------------------------------- #
def phases(hardware_name_key: str, open_label_key: str, open_target: str) -> PhaseSet:
    return PhaseSet(
        phases=(
            Phase(0, "pb_run_pipeline", kind="run"),
            Phase(100, "ph_validation", handler="validation", subs=(
                Sub(110, "pb_validate_iolist"),
                Sub(170, "pb_open_iolist", kind="open", opens="iolist"),
                Sub(190, "pb_open_val_logs", kind="open", opens="validation_logs"),
            )),
            Phase(700, hardware_name_key, handler="hardware", subs=(
                Sub(710, "pb_gen_stations"),
                Sub(720, "pb_gen_modules"),
                Sub(740, open_label_key, kind="open", opens=open_target),
            )),
        ),
        # Run-all: the documents judged first (a FAIL halts), then the hardware
        run_plan=(100, 700),
    )


# --------------------------------------------------------------------------------------------- #
# 100 Validation - the I/O List only
# --------------------------------------------------------------------------------------------- #
def run_validation(ctx, only=None):
    """Phase 100 of a generic-hardware type: the 110 I/O List checks with the system passed in (the
    `mandatory_in` columns of this type), the findings recorded and the four reports written as the
    Siemens 100 does (the same `runner` report path, 120-150 skipped: there is no second document)."""
    from pipeline5 import config
    from pipeline5.findings import messages, treatments
    from pipeline5.findings import report_renderer as iorender
    from pipeline5.phases.validation import iolist_checks as iolist
    from pipeline5.phases.validation import runner as validation
    params = config.load_params()
    label = i18n.tr("ph_validation", ctx.lang)
    ctx.emit("PHASE", f"{only or 100} {label}  (110)")
    ctx.status("validation…")
    with messages.active_lang(ctx.lang):
        findings = iolist.run_iolist(params, system=ctx.system)
    if only is not None:
        issues = [f for f in findings if f.severity in ("FAIL", "ERRR", "WARN")]
        ctx.render(findings, label=str(only))
        ctx.emit("RSLT", f"  {only}: {len(issues)} issues + {sum(1 for f in findings if f.severity == 'PASS')} PASS "
                         f"(log only; the 100 header writes the reports)")
        return
    res = validation.report_findings(findings, lang=ctx.lang)
    issues = [f for f in res["findings"] if f.severity in ("FAIL", "ERRR", "WARN")]
    applied = treatments.apply_and_reconcile(issues)
    ctx.records(iorender.render_records(res["items"]))
    if treatments.should_halt(applied):
        ctx.halt()
        ctx.emit("FAIL", "  100: FAIL findings in the I/O List - the pipeline HALTS here "
                         "(the reports are written; fix the document before building)")
    c = res["counts"]
    ctx.emit("RSLT", f"  100: {c.get('FAIL', 0)} FAIL, {c.get('ERRR', 0)} ERRR, {c.get('WARN', 0)} WARN, "
                     f"{c.get('PASS', 0)} PASS, {c.get('SKIP', 0)} SKIP -> {res['dir']}")


# --------------------------------------------------------------------------------------------- #
# 700 Hardware - TIA Portal (the siemens_s7 build + export) and SYCON.net (the hw/sycon-* handoff)
# --------------------------------------------------------------------------------------------- #
def run_hardware_tia(ctx, only=None):
    """The Siemens hardware chapter as it is (hardware.build + the hw/* BuilderData export); an I/O List
    without a PLC head cannot host a TIA hardware configuration - a pointed FAIL instead of the layout's
    RuntimeError."""
    from pipeline5.systems.plc_based.siemens_s7.safety import main as siemens
    try:
        siemens.run_hardware(ctx, only)
    except RuntimeError as ex:
        ctx.emit("FAIL", f"  700: {ex}")
        ctx.halt()


class SyconOutputLayout(OutputLayout):
    """The SYCON.net handoff folder under the project's output root (`SyconNetProjectInterface/`, the
    folder Sycon5App consumes) - the `hardware` key the 740 open button and the writer share."""

    def handoff_dir(self) -> str:
        from pipeline5 import config
        from pipeline5.systems.ipc_based.intervalzero_rtx import sycon_handoff
        return os.path.join(config.output_root(), sycon_handoff.FOLDER)

    def dirs(self) -> dict:
        from pipeline5 import config
        return {"hardware": self.handoff_dir(), "workspace": config.output_root()}

    def delivery_dirs(self, database) -> dict:
        return self.dirs()


SYCON_LAYOUT = SyconOutputLayout()


def run_hardware_sycon(ctx, only=None):
    """Phase 700 of the SYCON.net type: stage the I/O List, then write the hw/sycon-stations / hw/sycon-modules
    tables and the shipped device-types database (`sycon_handoff.project`) into the handoff folder. The
    handoff's own findings (a model not in the database, a duplicate name of station, no controller) are
    rendered; a FAIL halts. 710 / 720 share the one export (both tables come from one build)."""
    from pipeline5 import config
    from pipeline5.findings import gate as run
    from pipeline5.phases.staging import iolist as staging
    from pipeline5.systems.ipc_based.intervalzero_rtx import sycon_handoff
    label = {710: "710 Generate Stations", 720: "720 Generate Modules"}.get(
        only, f"700 {i18n.tr('ph_hardware_sycon', ctx.lang)}  (710 Stations + 720 Modules)")
    ctx.emit("PHASE", label)
    ctx.status("hardware…")
    params = config.load_params()
    database, findings = staging.stage(params, system=ctx.system, save=False)
    if not ctx.gate(findings, label="700 (300 staging)"):
        return
    rows = list(database["signals"]) if "signals" in database else []
    out_dir = SYCON_LAYOUT.handoff_dir()
    dtd = config.get_param(params, "sycon_device_types_db", "") or None
    update_ms = int(config.get_param(params, "sycon_update_time_ms", sycon_handoff.DEFAULT_UPDATE_TIME_MS)
                    or sycon_handoff.DEFAULT_UPDATE_TIME_MS)
    source = os.path.basename(str(config.get_param(params, "iolist_path", "") or "I/O List"))
    res = sycon_handoff.project(rows, out_dir, dtd, source_label=source, update_time_ms=update_ms)
    if res["findings"]:
        ctx.render(res["findings"], label="700 SYCON.net handoff")
    if run.has_blocking(res["findings"]):
        ctx.halt()
        ctx.emit("FAIL", "  700: FAIL findings in the handoff - fix the I/O List or the device-types database")
    ctx.emit("RSLT", f"  700: {res['stations']} stations (controller {res['controller'] or '-'}) + {res['modules']} "
                     f"module rows + {os.path.basename(res['device_types_db'])} -> {out_dir}")
