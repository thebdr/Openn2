"""The siemens_s7_safety MAIN ROUTINE - this system's whole pipeline, in one file.

Read it top to bottom and you have the system's operating manual: PHASES is the table of contents
(every phase-bar button + chevron sub-button, transcribed from the operator oracle
`Pipeline3App/assets/ButtonsLayout.xlsx`, with the explicit Run-all `run_plan`), and the `run_*`
handlers below it are the chapters - each one stages its prerequisites, runs its phase, and reports
through the PhaseContext seams. No handler touches Tk: the host (workbench/app_main) supplies
`ctx.emit/status/gate/render/halt`, which is why every phase button is also runnable HEADLESS
(tests/unit/test_siemens_main_handlers.py drives them against the real fixture documents).

Dispatch: a phase header click -> `HANDLERS[phase.handler](ctx)`; a dropdown action ->
`HANDLERS[...](ctx, only=<sub number>)`; an orange special -> `HANDLERS[sub.opens](ctx)`.
The stage->fill->re-stage wiring lives HERE (the run-plan), not in the fill chapter: `run_fill`
stages the source document, hands the staged database to `document_fill`, and the SSOT truth is
the NEXT staging pass over the re-written document (L2: chapters meet only in the truth tables).
"""
from __future__ import annotations

import os

from pipeline5.language import i18n
from pipeline5.systems.system_contract import Phase, PhaseSet, Sub

# --------------------------------------------------------------------------------------------- #
# The phase registry - bar order, Run-all first. Sub-buttons per the oracle ButtonsLayout.xlsx;
# deferred/unported ones are kept VISIBLE but enabled=False (greyed). Phase 200 (Documents Fill
# Out) IS built + wired; it is kept OUT of run_plan by design - it mutates the source document,
# so filling is a deliberate operator action (the 200 button), never a side-effect of Run-all.
# --------------------------------------------------------------------------------------------- #
PHASES = PhaseSet(
    phases=(
        Phase(0, "pb_run_pipeline", kind="run"),
        Phase(100, "ph_validation", handler="validation", requires=(300,), subs=(
            Sub(110, "pb_validate_iolist"),
            Sub(120, "pb_validate_ce"),
            Sub(130, "pb_xcheck_cem_iol"),
            Sub(140, "pb_xcheck_iol_cem"),
            Sub(150, "pb_validate_diag"),                                    # diagnosis checks (SKIPs on a virgin doc)
            Sub(155, "pb_clean_iolist", kind="special", enabled=False),      # clean.py not ported
            Sub(156, "pb_clean_cematrix", kind="special", enabled=False),
            Sub(160, "pb_open_errmgmt", kind="open", opens="error_mgmt"),
            Sub(170, "pb_open_iolist", kind="open", opens="iolist"),
            Sub(180, "pb_open_ce", kind="open", opens="matrix"),
            Sub(190, "pb_open_val_logs", kind="open", opens="validation_logs"),
        )),
        Phase(200, "ph_fill", handler="fill", subs=(
            Sub(210, "pb_fill_script_type"),                                 # CSV-rule classification
            Sub(220, "pb_fill_index"),                                       # §7 index
            Sub(230, "pb_fill_diag_cabinet"),                                # §8 diag cabinet
            Sub(240, "pb_fill_diag_bit"),                                    # §8 diag bit
            Sub(245, "pb_risky_index", kind="special", opens="risky_index"), # ORANGE manual fill (not in the pipeline)
            Sub(250, "pb_open_iolist", kind="open", opens="iolist"),
        )),
        Phase(300, "ph_staging", handler="staging", subs=(
            Sub(310, "pb_stage_iolist"),                                     # I/O List only (no C&E)
            Sub(320, "pb_stage_cematrix"),                                   # I/O List + C&E (the full staging)
            Sub(330, "pb_open_io_database", kind="open", opens="database"),
        )),
        Phase(400, "ph_interfaces", handler="interfaces", requires=(300, 520), subs=(
            Sub(410, "pb_gen_interfaces"),
            Sub(420, "pb_open_interfaces", kind="open", opens="interfaces"),
            Sub(430, "pb_gen_custom_iface", kind="special", enabled=False),  # GUI popup not built
        )),
        Phase(500, "ph_signals", handler="data_blocks", requires=(300,), subs=(
            Sub(510, "pb_gen_io_tags"),
            Sub(520, "pb_gen_data_blocks"),
            Sub(530, "pb_open_io_tags", kind="open", opens="io_tags"),
            Sub(540, "pb_open_data_blocks", kind="open", opens="blocks_import"),
        )),
        Phase(600, "ph_diagnosis", handler="diagnosis", requires=(300, 520), subs=(
            Sub(610, "pb_gen_diag_list"),
            Sub(620, "pb_gen_diag_swblocks"),
            Sub(630, "pb_open_diag_data", kind="open", opens="diaglist"),
            Sub(640, "pb_open_diag_config", kind="open", opens="diag_config"),
        )),
        Phase(700, "ph_hardware", handler="hardware", requires=(300,), subs=(
            Sub(710, "pb_gen_stations"),
            Sub(720, "pb_gen_modules"),
            Sub(730, "pb_open_hardware", kind="open", opens="hardware"),
        )),
        Phase(800, "ph_software", handler="software", requires=(300, 520), subs=(
            Sub(810, "pb_gen_shells", enabled=False),                        # editable shells deferred
            Sub(820, "pb_gen_blocks"),
            Sub(830, "pb_gen_instances"),
            Sub(840, "pb_open_builder_shells", kind="open", enabled=False, opens="blocks_creation"),
            Sub(850, "pb_open_blocks_folder", kind="open", opens="blocks_import"),
        )),
        Phase(900, "ph_reporting", handler="reporting", requires=(300,), subs=(
            Sub(910, "pb_gen_cov_pipeline"),
            Sub(920, "pb_gen_cov_tia", enabled=False),                       # 920 deferred (pending OP4 export)
            Sub(940, "pb_change_report"),                                    # before/after quality report (a REPORT)
            Sub(930, "pb_open_reports", kind="open", opens="coverage"),
        )),
    ),
    # Run-all, explicit: staging first, the builders ascending, then Reporting (reads every build)
    # and Validation. Each handler is self-contained (re-stages its own prerequisites), so the plan
    # drives the log narrative, not correctness. 200 Fill is deliberately absent (see above).
    run_plan=(300, 400, 500, 600, 700, 800, 900, 100),
)


# --------------------------------------------------------------------------------------------- #
# The phase handlers - each runs on the host's worker thread and reports ONLY through ctx.
# --------------------------------------------------------------------------------------------- #
def run_validation(ctx, only=None):
    """Phase 100 - the 4-step validation workflow (user spec): 1 validate doc 1 (110 I/O List),
    2 validate doc 2 if present (120 C&E), 3 cross-checks (130+140), 4 diagnosis checks (150 -
    requires a FILLED doc, SKIPs on a virgin one). only=None runs all + records the issues +
    writes the reports; only=<sub> runs just that validator to the log. A FAIL halts the
    pipeline after the reports are written (the severity contract)."""
    from pipeline5 import config
    from pipeline5.findings import treatments
    from pipeline5.phases.staging import iolist as staging
    from pipeline5.phases.validation import crosscheck, diagcheck
    from pipeline5.phases.validation import iolist_checks as iolist
    from pipeline5.phases.validation import cematrix_checks as matrix
    from pipeline5.phases.validation import runner as validation
    from pipeline5.findings import messages
    if only is None:
        from pipeline5.findings import report_renderer as iorender
        ctx.emit("PHASE", f"100 {i18n.tr('ph_validation', ctx.lang)}  (110 + 120 + 130 + 140 + 150)")
        ctx.status("validation…")
        database, _sf = staging.stage(system=ctx.system)
        res = validation.run_validation(database, lang=ctx.lang)
        issues = [f for f in res["findings"] if f.severity in ("FAIL", "ERRR", "WARN")]
        applied = treatments.apply_and_reconcile(issues)   # registry maintenance
        # the FULL report to the log - every level + the 110/120/130/140 sub-phase banners (the Levels
        # dropdown filters the view; a hidden level is elided, not dropped, and still reaches the tee).
        ctx.records(iorender.render_records(res["items"]))
        if treatments.should_halt(applied):        # the severity contract: FAIL halts the pipeline
            ctx.halt()
            ctx.emit("FAIL", "  100: FAIL findings in the documents - the pipeline HALTS here "
                             "(the reports are written; fix the documents before building)")
        c = res["counts"]
        ctx.emit("RSLT", f"  100: {c.get('FAIL', 0)} FAIL, {c.get('ERRR', 0)} ERRR, "
                         f"{c.get('WARN', 0)} WARN, {c.get('PASS', 0)} PASS, {c.get('SKIP', 0)} SKIP "
                         f"-> {res['dir']}")
        return
    ctx.emit("PHASE", f"{only} {i18n.tr(ctx.system.phases.sub_by_number(only).label_key, ctx.lang)}")
    ctx.status("validation…")
    params = config.load_params()
    with messages.active_lang(ctx.lang):      # build the finding detail in the operator's language
        if only == 110:
            findings = iolist.run_iolist(params)
        elif only == 120:
            findings = matrix.run_ce_matrix(params)
        elif only == 150:                      # diagnosis checks over the staged SSOT
            database, _sf = staging.stage(params, system=ctx.system)
            findings = diagcheck.run_diag_checks(database, params)
        else:                                  # 130 / 140 read the staged signals
            database, _sf = staging.stage(params, system=ctx.system)
            runner = crosscheck.run_xcheck_cem_iol if only == 130 else crosscheck.run_xcheck_iol_cem
            findings = runner(database, params)
    issues = [f for f in findings if f.severity in ("FAIL", "ERRR", "WARN")]
    ctx.render(findings, label=str(only))          # the FULL sub-phase log (all levels, elide-filtered)
    n_pass = sum(1 for f in findings if f.severity == "PASS")
    ctx.emit("RSLT", f"  {only}: {len(issues)} issues + {n_pass} PASS "
                     f"(log only; the 100 header writes the reports)")


def run_change_report(ctx, only=None):
    """Phase 900 sub (940) - the STANDALONE before/after quality report (not part of the pipeline).
    Reads the configured current + previous document revisions (`*_previous_path`), classifies the
    changes (matched / intact / corrected / upgrade / removed; systematic re-schemes netted out), and
    writes a graphical HTML dashboard + a CSV audit trail. Never halts; opens the report when done."""
    from pipeline5.phases.changes import report_runner as changes_run
    label = f"940 {i18n.tr('pb_change_report', ctx.lang)}"
    ctx.emit("PHASE", label)
    ctx.status("quality report…")
    res = changes_run.run_change_report()
    iol = res["result"].get("iolist", {})
    if iol.get("available"):
        ctx.emit("RSLT", f"  IoList: {iol['intact']} intact, {iol['correction_count']} corrections "
                         f"({len(iol['regressions'])} value-loss), {iol['upgrade_rows']} upgrade rows, "
                         f"{len(iol['removed'])} removed -> {os.path.basename(res['paths']['html'])}")
    else:
        ctx.emit("INFO", "  no prior I/O List revision configured (set iolist_previous_path in "
                         f"project_params.yaml) -> {res['dir']}")
    try:
        os.startfile(res["paths"]["html"])           # open the report in the default browser
    except Exception:                                # noqa: BLE001 - opening is best-effort
        pass


def run_fill(ctx, only=None):
    """Phase 200 - Documents Fill Out. The RUN-PLAN wiring: stage the source I/O List (the read),
    hand the staged database to the fill chapter, which computes 210 classify (AB Script Type /
    AC Suggested Type), 220 §7 Index (AD), 230/240 §8 Diag Cabinet/Bit (AE/AF) + the DiagnosisBlocks
    sheet and writes them back IN PLACE (surgical, timestamped backup deleted on a value-identical
    no-op). The phase-200 header runs all four; a sub-phase button runs just its leg (230/240 are
    paired). ph200 writes the DOC only; the SSOT truth is the NEXT staging pass over the filled doc.
    An unresolved row (`<input required>`) is a blocking finding (the `_UnresolvedIndex` sheet)."""
    from pipeline5.phases.fillout import document_fill as fill
    from pipeline5.phases.staging import iolist as staging
    ctx.status("fill…")
    keys = {210: "pb_fill_script_type", 220: "pb_fill_index",
            230: "pb_fill_diag_cabinet", 240: "pb_fill_diag_bit"}
    label = f"{only or 200} {i18n.tr(keys.get(only, 'ph_fill'), ctx.lang)}"
    ctx.emit("PHASE", label)
    database, _sf = staging.stage(system=ctx.system)   # the READ of the source doc (stage #1)
    res = fill.fill_out(database, only=only)
    if not ctx.gate(res["findings"], label=label):
        return
    backup = f"  (backup {os.path.basename(res['backup'])})" if res["backup"] else "  (no change)"
    ctx.emit("RSLT", f"  filled {res['filled']} script type(s), {res['index']} index, {res['diag']} "
                     f"diag; {res['mismatch']} kept (Mode-2); {res['unresolved']} unresolved -> "
                     f"{os.path.basename(res['output_path'])}{backup}")


def run_risky_index(ctx, only=None):
    """The MANUAL 'Risky Index Fill' (orange, NOT in the pipeline): over the already-filled I/O List, fill
    each <input required> index by matching it to an existing object index of the same family in the same
    IO node (positional address range), per script_type by ROW ORDER. The filled cells are written RED +
    listed in a `_RiskyIndex` review sheet. A row-order GUESS - REVIEW the sheet."""
    from pipeline5.phases.fillout import document_fill as fill
    from pipeline5.phases.staging import iolist as staging
    ctx.status("risky index…")
    label = f"245 {i18n.tr('pb_risky_index', ctx.lang)}"
    ctx.emit("PHASE", label)
    database, _sf = staging.stage(system=ctx.system)   # the read of the (already-filled) source doc
    res = fill.risky_index_fill(database)
    ctx.render(res["findings"], label="245 risky index")           # doc already written
    backup = f"  (backup {os.path.basename(res['backup'])})" if res.get("backup") else "  (no change)"
    ctx.emit("WARN", f"  RISKY: filled {res['filled']} index cell(s) by node row-order; "
                     f"{res.get('leftover', 0)} left unresolved -> "
                     f"{os.path.basename(res['output_path'])}{backup}. REVIEW the _RiskyIndex sheet.")


def run_staging(ctx, only=None):
    """Phase 300: stage the configured I/O List -> the signals table -> Database/signals.csv. The oracle
    splits it: 310 Stage I/O List (`stage_iolist` - I/O List only, no C&E) / 320 Stage C&E Matrix (the
    full staging = I/O List + the Cause&Effect enrichment). 300/320 are byte-identical to the monolith."""
    from pipeline5 import config
    from pipeline5.phases.staging import iolist as staging
    ctx.status("staging…")
    if only == 310:
        ctx.emit("PHASE", f"310 {i18n.tr('pb_stage_iolist', ctx.lang)}")
        database, findings = staging.stage_iolist(system=ctx.system)
        label = "310 Stage I/O List"
    else:
        key = "pb_stage_cematrix" if only == 320 else "ph_staging"
        ctx.emit("PHASE", f"{only or 300} {i18n.tr(key, ctx.lang)}")
        database, findings = staging.stage(system=ctx.system)
        label = f"{only or 300} staging"
    if not ctx.gate(findings, label=label):
        return
    signals = database["signals"]
    suffix = "  (I/O List only - run 320 for the C&E)" if only == 310 else ""
    ctx.emit("RSLT", f"  staged {len(signals)} signals{suffix} "
                     f"-> {os.path.join(config.database_dir(), 'signals.csv')}")


def run_data_blocks(ctx, only=None):
    """Phase 500. only=520: stage -> 520 (db_members/db_blocks/instance_dbs + write-back) -> the GlobalDB
    XML. only=510: + build the interface tables and project PLCTags.xlsx. only=None: both. (510 needs the
    520 write-back, so 520 is always built; it's only PROJECTED when 520/None is requested.)"""
    from pipeline5 import config
    from pipeline5.findings import gate as run
    from pipeline5.phases.staging import iolist as staging
    from pipeline5.phases.datablocks import generator as datablocks
    from pipeline5.systems.plc_based.siemens_s7 import globaldb_xml_emitter as datablock_xml
    from pipeline5.phases.interfaces import builder as interfaces
    from pipeline5.systems.plc_based.siemens_s7 import plctags_xlsx_writer as io_tags
    label = {510: "510 Generate I/O Tags", 520: "520 Generate Data Blocks"}.get(
        only, "500 Signals Mapping  (520 Data Blocks + 510 I/O Tags)")
    ctx.emit("PHASE", label)
    ctx.status("data blocks…")
    findings = []
    database, f = staging.stage(system=ctx.system); findings += f
    if not run.has_blocking(f):
        database, f = datablocks.build(database, system=ctx.system); findings += f
    if not ctx.gate(findings, label="500 (300 staging + 520 data blocks)"):
        return
    if "db_blocks" not in database:
        ctx.emit("WARN", "  520 produced no tables (a blocking prereq was downgraded but yielded no data) - nothing further")
        return
    if only in (None, 520):
        n_dbs, n_members = len(database["db_blocks"]), len(database["db_members"])
        ctx.emit("RSLT", f"  {n_members} db_members across {n_dbs} DBs (+ {len(database['instance_dbs'])} "
                         f"instance DBs) -> {os.path.join(config.database_dir(), 'db_members.csv')}")
        count = datablock_xml.project(database)
        ctx.emit("RSLT", f"  projected {count} GlobalDB XMLs -> {config.blocks_import_dir()}")
    if only in (None, 510):
        ctx.status("I/O tags…")
        database, iface_findings = interfaces.build_interfaces(database)
        res = io_tags.project(database)
        if not res["path"]:               # duplicate tags: the raw-FAIL guard skipped the write
            if ctx.gate(iface_findings + res["findings"], label="510 I/O tags"):
                ctx.emit("WARN", "  510: the duplicate-tag FAILs are downgraded in the registry, "
                                 "but PLCTags.xlsx is never written on a raw FAIL - fix the I/O List rows")
            return
        ctx.render(iface_findings + res["findings"], label="510 I/O tags")
        ctx.emit("RSLT", f"  510: {res['total']} I/O tags ({res['io_count']} signal + "
                         f"{res['iface_count']} interface) across {len(res['tables'])} tables -> {config.io_tags_dir()}")


def run_interfaces(ctx, only=None):
    """Phase 400: stage -> 520 -> the interfaces/interface_elements tables -> the IF_*.xlsx projection
    -> (gated) insert each as an IF_ sheet into the I/O List. (410 == the whole phase.)"""
    from pipeline5 import config
    from pipeline5.findings import gate as run
    from pipeline5.phases.staging import iolist as staging
    from pipeline5.phases.datablocks import generator as datablocks
    from pipeline5.phases.interfaces import builder as interfaces
    from pipeline5.systems.plc_based.siemens_s7 import interface_xlsx_writer as interface_xlsx
    ctx.emit("PHASE", "410 Generate Interfaces" if only == 410 else "400 Interfaces Generation")
    ctx.status("interfaces…")
    findings = []
    database, f = staging.stage(system=ctx.system); findings += f
    if not run.has_blocking(f):
        database, f = datablocks.build(database, system=ctx.system); findings += f
    if not ctx.gate(findings, label="400 (300 staging + 520 prereq)"):
        return
    if "db_blocks" not in database:
        ctx.emit("WARN", "  520 prereq produced no tables (a blocking finding was downgraded but yielded no data) - nothing further")
        return
    database, iface_findings = interfaces.build_interfaces(database)
    ctx.render(iface_findings, label="400 interfaces")
    result = interface_xlsx.project(database)
    n_if, n_el = len(database["interfaces"]), len(database["interface_elements"])
    ctx.emit("RSLT", f"  {n_if} interfaces, {n_el} mirrored elements -> {len(result['created'])} "
                     f"IF_*.xlsx in {config.interfaces_dir()}")
    from pipeline5.systems.plc_based.siemens_s7 import interface_scl_emitter as interface_scl
    scl = interface_scl.project(database)
    ctx.render(scl["findings"], label="430 MachineInterfaces SCL")
    if scl["path"]:
        ctx.emit("RSLT", f"  MachineInterfaces SCL: {scl['assignments']} assignments across "
                         f"{scl['interfaces']} interfaces -> {scl['path']}")
    params = config.load_params()
    if config.get_param(params, "iolist_params.insert_interface_sheets", False):
        ctx.status("inserting IF_ sheets…")
        for action in interface_xlsx.insert_interface_sheets(database, iolist_path=params.get("iolist_path")):
            ctx.emit("WARN" if action.startswith("[WARN]") else "INFO", f"  {action}")
    else:
        ctx.emit("INFO", "  insert_interface_sheets: disabled (iolist_params.insert_interface_sheets)")


def run_diagnosis(ctx, only=None):
    """Phase 600: stage -> 520 build -> diagnosis.build, then project 610 DiagList_IO/Logic.csv and/or
    620 the OPC SCL. only=610/620 projects just that surface; None does both. (Both need diagnosis.build,
    so it always runs.)"""
    from pipeline5 import config
    from pipeline5.findings import gate as run
    from pipeline5.phases.staging import iolist as staging
    from pipeline5.phases.datablocks import generator as datablocks
    from pipeline5.phases.diagnosis import builder as diagnosis
    from pipeline5.phases.diagnosis import diaglist as diaglist_csv
    from pipeline5.systems.plc_based.siemens_s7.safety import opc_diagnosis_scl as diagnosis_scl
    label = {610: "610 Generate Diag List", 620: "620 Generate Diag Software Blocks"}.get(
        only, "600 Diagnosis Mapping  (610 DiagList + 620 OPC SCL)")
    ctx.emit("PHASE", label)
    ctx.status("diagnosis…")
    findings = []
    database, f = staging.stage(system=ctx.system); findings += f
    if not run.has_blocking(f):
        database, f = datablocks.build(database, system=ctx.system); findings += f
    if not ctx.gate(findings, label="600 (300 staging + 520 prereq)"):
        return
    if "db_blocks" not in database:
        ctx.emit("WARN", "  520 prereq produced no tables (a blocking finding was downgraded but yielded no data) - nothing further")
        return
    database, diag_findings = diagnosis.build(database)
    rendered, res, scl = list(diag_findings), None, None
    if only in (None, 610):
        res = diaglist_csv.project(database); rendered += res["findings"]
    if only in (None, 620):
        scl = diagnosis_scl.project(database); rendered += scl["findings"]
    ctx.render(rendered, label="600 diagnosis")
    if res is not None:
        ctx.emit("RSLT", f"  610 DiagList: {res['io_count']} IO + {res['logic_count']} logic rows -> {config.diaglist_dir()}")
    if scl is not None and scl["path"]:
        ctx.emit("RSLT", f"  620 OPC SCL: {scl['entries']} entries across {scl['cabinets']} cabinets -> {scl['path']}")


def run_hardware(ctx, only=None):
    """Phase 700: stage -> hardware.build -> hardware_csv.project (format-2 Stations.csv + Modules.csv).
    710/720 share one extract and each writes BOTH CSVs (like PL3), so only= just changes the label."""
    from pipeline5 import config
    from pipeline5.findings import gate as run
    from pipeline5.phases.staging import iolist as staging
    from pipeline5.systems.plc_based.siemens_s7 import profinet_hardware as hardware
    from pipeline5.systems.plc_based.siemens_s7 import hardware_csv_export as hardware_csv
    label = {710: "710 Generate Stations", 720: "720 Generate Modules"}.get(
        only, "700 Hardware Generation  (710 Stations + 720 Modules)")
    ctx.emit("PHASE", label)
    ctx.status("hardware…")
    findings = []
    database, f = staging.stage(system=ctx.system); findings += f
    if not run.has_blocking(f):
        database, f = hardware.build(database); findings += f
    if not ctx.gate(findings, label="700 (300 staging + hardware)"):
        return
    if "hardware_stations" not in database:
        ctx.emit("WARN", "  700 produced no tables (a blocking finding) - nothing further")
        return
    res = hardware_csv.project(database)
    ctx.emit("RSLT", f"  700: {res['stations']} stations + {res['modules']} modules -> {config.hardware_dir()}")


def run_software(ctx, only=None):
    """Phase 800: stage -> 520 -> engine.build. only=820 projects the CreationInfo CSVs + the 03 FC
    XML; only=830 writes InstanceDBs.csv; None does both. (engine.build always runs - both surfaces
    project from it. 02_COM/05_EM_STATE are ordinary 520 config DBs - the 500 leg projects them.)"""
    from pipeline5 import config
    from pipeline5.findings import gate as run
    from pipeline5.phases.staging import iolist as staging
    from pipeline5.phases.datablocks import generator as datablocks
    from pipeline5.phases.software_blocks import build_engine as engine
    label = {820: "820 Generate Blocks", 830: "830 Generate Instances"}.get(
        only, "800 Software Generation  (820 Blocks + 830 Instances + 03 FC XML)")
    ctx.emit("PHASE", label)
    ctx.status("software…")
    findings = []
    database, f = staging.stage(system=ctx.system); findings += f
    if not run.has_blocking(f):
        database, f = datablocks.build(database, system=ctx.system); findings += f
    if not ctx.gate(findings, label="800 (300 staging + 520 prereq)"):
        return
    if "db_blocks" not in database:
        ctx.emit("WARN", "  520 prereq produced no tables (a blocking finding was downgraded but yielded no data) - nothing further")
        return
    database, blk_findings = engine.build(database, system=ctx.system)
    # the verbose per-block log (user spec): each generated block, its template (when a shipped
    # one exists), the declared output surface, and the builder function that produced it
    surface = {"csv": "CreationInfo CSV", "fc_xml": "FC XML (ImportReady)",
               "scl": "SCL (ImportReady)"}
    for r in engine.block_report(database, ctx.system):
        tmpl = f"  template={r['template_stem']}" if r["template_stem"] else ""
        inst_note = f" + {r['instances']} instance DBs" if r["instances"] else ""
        ctx.emit("INFO", f"  {r['name']}  <-  {r['builder']}(){tmpl}  ->  "
                         f"{surface.get(r['emit'], r['emit'])}, {r['rows']} rows{inst_note}")
    rendered, res, inst = list(blk_findings), None, None
    if only in (None, 820):
        res = engine.project(database, system=ctx.system); rendered += res["findings"]
    if only in (None, 830):
        inst = engine.write_instance_dbs(database)
    ctx.render(rendered, label="800 software")
    if res is not None:
        ctx.emit("RSLT", f"  820: {len(database['software_blocks'])} blocks -> {res['count']} "
                         f"CreationInfo CSVs + {len(res['xml_files'])} FC XML + "
                         f"{len(res.get('scl_files', []))} SCL -> {config.blocks_creation_dir()}")
    if inst is not None:
        ctx.emit("RSLT", f"  830 InstanceDBs: {inst['count']} instance DBs -> {inst['path']}")


def run_reporting(ctx, only=None):
    """Phase 900: build the full SSOT (stage -> 520 -> 700; then the WARN-only 400/600/800) then
    coverage.build (the coverage table + ORPHAN/UNPLACED findings) -> coverage.project (the reports).
    (910 == the whole phase; 940 = the standalone before/after quality report - it is a REPORT, not
    a document check.)"""
    if only == 940:
        return run_change_report(ctx)
    from pipeline5 import config
    from pipeline5.findings import gate as run
    from pipeline5.phases.staging import iolist as staging
    from pipeline5.phases.datablocks import generator as datablocks
    from pipeline5.phases.interfaces import builder as interfaces
    from pipeline5.phases.diagnosis import builder as diagnosis
    from pipeline5.systems.plc_based.siemens_s7 import profinet_hardware as hardware
    from pipeline5.phases.coverage import coverage
    from pipeline5.phases.software_blocks import build_engine as engine
    ctx.emit("PHASE", "910 Generate Pipeline Coverage Report" if only == 910 else "900 Reporting  (910 Pipeline Coverage)")
    ctx.status("coverage…")
    findings = []
    database, f = staging.stage(system=ctx.system); findings += f
    if not run.has_blocking(findings):
        database, f = datablocks.build(database, system=ctx.system); findings += f
    if not run.has_blocking(findings):
        database, f = hardware.build(database); findings += f
    if not ctx.gate(findings, label="900 (300 + 520 + 700 prereqs)"):
        return
    if "db_blocks" not in database:
        ctx.emit("WARN", "  a blocking prereq was downgraded but yielded no data - nothing further")
        return
    proj = []
    database, fi = interfaces.build_interfaces(database); proj += fi
    database, fd = diagnosis.build(database); proj += fd
    database, fb = engine.build(database, system=ctx.system); proj += fb
    database, fc = coverage.build(database, system=ctx.system); proj += fc
    res = coverage.project(database, system=ctx.system)
    ctx.render(proj, label="900 coverage")
    st = res["stats"]
    ctx.emit("RSLT", f"  910 coverage: {st['rows']} rows (sig {st['kinds']['signal']}/"
                     f"chan {st['kinds']['channel']}/struct {st['kinds']['structural']}), "
                     f"{st['orphans']} ORPHAN, {st['unplaced']} UNPLACED -> {res['txt']}")


# The dispatch table System.handlers carries - Phase.handler / a special Sub.opens key -> handler.
HANDLERS = {
    "validation": run_validation,
    "fill": run_fill,
    "risky_index": run_risky_index,
    "staging": run_staging,
    "interfaces": run_interfaces,
    "data_blocks": run_data_blocks,
    "diagnosis": run_diagnosis,
    "hardware": run_hardware,
    "software": run_software,
    "reporting": run_reporting,
}
