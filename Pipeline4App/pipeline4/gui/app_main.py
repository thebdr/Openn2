"""The PL4 operator window: a toolbar, the phase-button bar, and a Log notebook.

M0 of the GUI port: phases now run on a WORKER THREAD - the handler runs off the Tk main thread and posts
its log/status through a `queue.Queue` drained by `root.after`, so a real run no longer freezes the window
(an indeterminate progressbar + greyed phase buttons mark a run in flight). The phase bar + the dispatch +
Run-all are driven by the `gui/phases.py` registry (one source of the phase order). The log lives in a
`ttk.Notebook` so the Findings / Database Explorer / Files tabs slot in with later milestones.

The backend is fully wired: every phase button runs its real phase. A handler emits via `self._emit`
(thread-safe enqueue) / `self._status` and must NOT touch Tk widgets directly (the drain pump applies them
on the main thread).
"""
from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
import traceback
from tkinter import ttk

from pipeline4.core import config, severity, treatments
from pipeline4.gui import excel, findings_view, phases, theme
from pipeline4.gui.db_explorer import DatabaseExplorer
from pipeline4.gui.findings_panel import FindingsPanel
from pipeline4.gui.logview import LogView
from pipeline4.gui.phasebar import PhaseBar

APP_TITLE = "Pipeline4 - SSOT database build"


class App:
    def __init__(self, root):
        self.root = root
        self.mode = "dark"
        self._busy = False
        self._q: queue.Queue = queue.Queue()
        root.title(APP_TITLE)
        root.geometry("1180x720")
        backend = theme.apply_theme(root, self.mode)

        toolbar = ttk.Frame(root)
        toolbar.pack(side="top", fill="x", padx=8, pady=(8, 4))
        ttk.Label(toolbar, text="PIPELINE4", font=("Consolas", 13, "bold")).pack(side="left", padx=(2, 14))
        ttk.Button(toolbar, text="Theme", command=self._toggle_theme).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Clear Log", command=self._clear).pack(side="left", padx=2)
        self._level_vars = {}                     # the Levels dropdown: a checkbutton per severity level
        levels_mb = ttk.Menubutton(toolbar, text="Levels ▾")
        levels_menu = tk.Menu(levels_mb, tearoff=0)
        shown0 = config.load_app_ui()["log_levels"]
        for level in severity.LEVELS:             # FAIL, ERROR, WARN, INFO, SKIP, PASS, DEBUG
            forced = level in ("FAIL", "ERROR")   # always shown, greyed out (can't be disabled)
            var = tk.BooleanVar(value=forced or level in shown0)
            self._level_vars[level] = var
            levels_menu.add_checkbutton(label=level, variable=var, command=self._on_levels_changed,
                                        state="disabled" if forced else "normal")
        levels_mb.configure(menu=levels_menu)
        levels_mb.pack(side="left", padx=6)
        self._backend_label = ttk.Label(toolbar, text=f"theme: {backend}")
        self._backend_label.pack(side="right", padx=2)

        self.phasebar = PhaseBar(root, self._on_phase)
        self.phasebar.pack(side="top", fill="x", padx=8, pady=2)

        # the status bar + the busy progressbar live at the bottom (progress just above the status line).
        self.status = ttk.Label(root, text="Ready", anchor="w", relief="sunken")
        self.status.pack(side="bottom", fill="x")
        self.progress = ttk.Progressbar(root, mode="indeterminate")
        self.progress.pack(side="bottom", fill="x")

        # the Log notebook (Findings / Database Explorer / Files tabs join here in later milestones).
        self.notebook = ttk.Notebook(root)
        log_tab = ttk.Frame(self.notebook)
        self.log = LogView(log_tab, shown_levels=config.load_app_ui()["log_levels"],
                           on_link=self._on_link, on_errtreat=self._on_errtreat)
        self.log.pack(side="top", fill="both", expand=True)
        self.notebook.add(log_tab, text="Log")
        findings_tab = ttk.Frame(self.notebook)
        self.findings = FindingsPanel(findings_tab)
        self.findings.pack(side="top", fill="both", expand=True)
        self.notebook.add(findings_tab, text="Findings")
        explorer_tab = ttk.Frame(self.notebook)
        self.explorer = DatabaseExplorer(explorer_tab)
        self.explorer.pack(side="top", fill="both", expand=True)
        self.notebook.add(explorer_tab, text="Database Explorer")
        self.notebook.pack(side="top", fill="both", expand=True, padx=8, pady=6)

        self.log.append("PHASE", "Pipeline4 - SSOT database build")
        self.log.append("INFO", f"theme backend: {backend}")
        self.log.append("INFO", "Click a phase to run it (on a worker thread), or Run Pipeline for all.")

        self.root.after(50, self._drain)

    # --- the worker-thread run plumbing --------------------------------------------------------- #
    def _emit(self, level: str, message: str) -> None:
        """Thread-safe log sink - enqueue a line for the drain pump (used by handlers + run.gate/render)."""
        self._q.put(("log", level, message))

    def _status(self, text: str) -> None:
        self._q.put(("status", text))

    def _on_phase(self, number, label):
        """A phase-bar click (main thread): start the phase on a worker thread (one at a time)."""
        if self._busy:
            self.log.append("WARN", "  a phase is already running - wait for it to finish")
            return
        self._set_busy(True)
        threading.Thread(target=self._worker, args=(number, label), daemon=True).start()

    def _worker(self, number, label):
        """Runs OFF the main thread: dispatch to the phase handler (or Run-all); never touch Tk here."""
        try:
            if number == 0:
                self._run_all()
            else:
                phase = phases.by_number(number)
                handler = getattr(self, phase.handler, None) if (phase and phase.handler) else None
                if handler is None:
                    self._emit("PHASE", f"{number} {label}")
                    self._emit("WARN", f"  phase {number} not implemented yet")
                else:
                    handler()
        except Exception:  # noqa: BLE001 - a handler crash must never take the window down
            self._emit("ERROR", f"handler for {label} crashed:\n{traceback.format_exc()}")
        finally:
            self._q.put(("done",))

    def _run_all(self):
        """Run every runnable phase in dependency order (each handler is self-contained / re-stages; M4
        will optimize to a stage-once shared database)."""
        self._emit("PHASE", "Run Pipeline (all phases)")
        for number in phases.run_order():
            getattr(self, phases.by_number(number).handler)()
        self._emit("PASS", "  Run Pipeline complete")

    def _drain(self):
        """Main thread: apply the queued log/status/done events to the widgets, then reschedule."""
        try:
            while True:
                event = self._q.get_nowait()
                kind = event[0]
                if kind == "log":
                    self.log.append(event[1], event[2])
                elif kind == "records":
                    self.log.append_records(event[1])
                elif kind == "status":
                    self.status.configure(text=event[1])
                elif kind == "done":
                    self._set_busy(False)
                    self.status.configure(text="Ready")
                    self.findings.refresh()          # surface the run's findings in the panel
                    self.explorer.refresh()          # reload the SSOT tables the run (re)wrote
        except queue.Empty:
            pass
        self.root.after(50, self._drain)

    def _set_busy(self, busy: bool):
        self._busy = busy
        self.phasebar.set_enabled(not busy)
        if busy:
            self.progress.start(12)
        else:
            self.progress.stop()

    # --- the GUI gate/render seam (structured, clickable records) -------------------------------- #
    def _gate(self, findings, *, label: str) -> bool:
        """Apply the registry, post the EFFECTIVE-severity findings as structured records to the log, and
        return CONTINUE (False = halt on a blocking effective severity). The records render on the worker
        (pure) and are drained into the clickable LogView on the main thread."""
        applied, recs = findings_view.apply_and_records(findings)
        self._q.put(("records", recs))
        if treatments.should_halt(applied):
            self._emit("FAIL", f"  {label} halted on a blocking finding - nothing written")
            return False
        return True

    def _render(self, findings) -> None:
        """Apply the registry + post the EFFECTIVE-severity findings as structured records (never halts)."""
        _applied, recs = findings_view.apply_and_records(findings)
        self._q.put(("records", recs))

    # --- log link callbacks (main thread) ------------------------------------------------------- #
    def _resolve_doc(self, basename: str) -> str:
        params = config.load_params()
        for path in (params.get("iolist_path"), params.get("matrix_path")):
            if path and os.path.basename(path) == basename:
                return path
        return ""

    def _on_link(self, doc, sheet, cell) -> None:
        """A clicked Sheet!Cell log link -> open the workbook in Excel at that cell (off-thread; COM)."""
        path = self._resolve_doc(doc)
        if not path:
            self.log.append("WARN", f"  cannot locate workbook '{doc}'")
            return
        threading.Thread(target=lambda: excel.goto(path, sheet, cell), daemon=True).start()

    def _on_errtreat(self, uid, level) -> None:
        """A right-click treat on a finding line -> set the treatment + refresh the Findings panel."""
        treatments.set_treatment(uid, level)
        self.findings.refresh()
        self.log.append("INFO", f"  treated {uid} -> {level or 'cleared'} (effective on the next run)")

    # --- the phase handlers (run on the worker thread; emit via self._emit / self._status) ------- #
    def _run_validation(self):
        """Phase 100: stage -> the 4 validators -> record the issues + write the 4 reports -> render the
        issues to the log. Never halts (a validation FAIL is reported, not blocking)."""
        from pipeline4.core import config, run
        from pipeline4.domain import staging
        from pipeline4.domain.validation import phase as validation
        self._emit("PHASE", "100 Documents Validation  (110 I/O List + 120 C&E + 130/140 cross-checks)")
        self._status("validation…")
        database, _sf = staging.stage()
        res = validation.run_validation(database)
        issues = [f for f in res["findings"] if f.severity in ("FAIL", "ERROR", "WARN")]
        self._render(issues)
        c = res["counts"]
        self._emit("PASS", f"  100: {c.get('FAIL', 0)} FAIL, {c.get('ERROR', 0)} ERROR, {c.get('WARN', 0)} WARN, "
                           f"{c.get('PASS', 0)} PASS, {c.get('SKIP', 0)} SKIP -> {res['dir']}")

    def _run_staging(self):
        """Phase 300: read the configured I/O List -> the signals table -> Database/signals.csv."""
        from pipeline4.core import config, run
        from pipeline4.domain import staging
        self._emit("PHASE", "300 Documents Staging")
        self._status("staging…")
        database, findings = staging.stage()
        if not self._gate(findings, label="300 Documents Staging"):
            return
        signals = database["signals"]
        self._emit("PASS", f"  staged {len(signals)} signals -> {os.path.join(config.database_dir(), 'signals.csv')}")

    def _run_data_blocks(self):
        """Phase 500: stage -> 520 (db_members/db_blocks/instance_dbs + the write-back) -> the GlobalDB XML;
        then 510 builds the interface tables and projects PLCTags.xlsx."""
        from pipeline4.core import config, run
        from pipeline4.domain import staging, datablocks, datablock_xml, interfaces, io_tags
        self._emit("PHASE", "500 Signals Mapping  (520 Data Blocks + 510 I/O Tags)")
        self._status("data blocks…")
        findings = []
        database, f = staging.stage(); findings += f
        if not run.has_blocking(f):
            database, f = datablocks.build(database); findings += f
        if not self._gate(findings, label="500 (300 staging + 520 data blocks)"):
            return
        if "db_blocks" not in database:
            self._emit("WARN", "  520 produced no tables (a blocking prereq was downgraded but yielded no data) - nothing further")
            return
        n_dbs, n_members = len(database["db_blocks"]), len(database["db_members"])
        self._emit("PASS", f"  {n_members} db_members across {n_dbs} DBs (+ {len(database['instance_dbs'])} "
                           f"instance DBs) -> {os.path.join(config.database_dir(), 'db_members.csv')}")
        count = datablock_xml.project(database)
        self._emit("PASS", f"  projected {count} GlobalDB XML(s) -> {config.blocks_import_dir()}")
        self._status("I/O tags…")
        database, iface_findings = interfaces.build_interfaces(database)
        res = io_tags.project(database)
        self._render(iface_findings + res["findings"])
        self._emit("PASS", f"  510: {res['total']} I/O tags ({res['io_count']} signal + "
                           f"{res['iface_count']} interface) across {len(res['tables'])} tables -> {config.io_tags_dir()}")

    def _run_interfaces(self):
        """Phase 400: stage -> 520 -> the interfaces/interface_elements tables -> the IF_*.xlsx projection
        -> (gated) insert each as an IF_ sheet into the I/O List."""
        from pipeline4.core import config, run
        from pipeline4.domain import staging, datablocks, interfaces, interface_xlsx
        self._emit("PHASE", "400 Interfaces Generation")
        self._status("interfaces…")
        findings = []
        database, f = staging.stage(); findings += f
        if not run.has_blocking(f):
            database, f = datablocks.build(database); findings += f
        if not self._gate(findings, label="400 (300 staging + 520 prereq)"):
            return
        if "db_blocks" not in database:
            self._emit("WARN", "  520 prereq produced no tables (a blocking finding was downgraded but yielded no data) - nothing further")
            return
        database, iface_findings = interfaces.build_interfaces(database)
        self._render(iface_findings)
        result = interface_xlsx.project(database)
        n_if, n_el = len(database["interfaces"]), len(database["interface_elements"])
        self._emit("PASS", f"  {n_if} interfaces, {n_el} mirrored elements -> {len(result['created'])} "
                           f"IF_*.xlsx in {config.interfaces_dir()}")
        params = config.load_params()
        if config.get_param(params, "iolist_params.insert_interface_sheets", False):
            self._status("inserting IF_ sheets…")
            for action in interface_xlsx.insert_interface_sheets(database, iolist_path=params.get("iolist_path")):
                self._emit("WARN" if action.startswith("[WARN]") else "INFO", f"  {action}")
        else:
            self._emit("INFO", "  insert_interface_sheets: disabled (iolist_params.insert_interface_sheets)")

    def _run_diagnosis(self):
        """Phase 600: stage -> 520 build -> diagnosis.build -> 610 DiagList_IO/Logic.csv -> 620 the OPC SCL."""
        from pipeline4.core import config, run
        from pipeline4.domain import staging, datablocks, diagnosis, diaglist_csv, diagnosis_scl
        self._emit("PHASE", "600 Diagnosis Mapping  (610 DiagList + 620 OPC SCL)")
        self._status("diagnosis…")
        findings = []
        database, f = staging.stage(); findings += f
        if not run.has_blocking(f):
            database, f = datablocks.build(database); findings += f
        if not self._gate(findings, label="600 (300 staging + 520 prereq)"):
            return
        if "db_blocks" not in database:
            self._emit("WARN", "  520 prereq produced no tables (a blocking finding was downgraded but yielded no data) - nothing further")
            return
        database, diag_findings = diagnosis.build(database)
        res = diaglist_csv.project(database)
        scl = diagnosis_scl.project(database)
        self._render(diag_findings + res["findings"] + scl["findings"])
        self._emit("PASS", f"  610 DiagList: {res['io_count']} IO + {res['logic_count']} logic rows -> {config.diaglist_dir()}")
        if scl["path"]:
            self._emit("PASS", f"  620 OPC SCL: {scl['entries']} entries across {scl['cabinets']} cabinets -> {scl['path']}")

    def _run_hardware(self):
        """Phase 700: stage -> hardware.build -> hardware_csv.project (format-2 Stations.csv + Modules.csv)."""
        from pipeline4.core import config, run
        from pipeline4.domain import staging, hardware, hardware_csv
        self._emit("PHASE", "700 Hardware Generation  (710 Stations + 720 Modules)")
        self._status("hardware…")
        findings = []
        database, f = staging.stage(); findings += f
        if not run.has_blocking(f):
            database, f = hardware.build(database); findings += f
        if not self._gate(findings, label="700 (300 staging + hardware)"):
            return
        if "hardware_stations" not in database:
            self._emit("WARN", "  700 produced no tables (a blocking finding) - nothing further")
            return
        res = hardware_csv.project(database)
        self._emit("PASS", f"  700: {res['stations']} station(s) + {res['modules']} module(s) -> {config.hardware_dir()}")

    def _run_software(self):
        """Phase 800: stage -> 520 -> 800 build -> project (CreationInfo CSVs + the 03 FC XML) ->
        write the 02_COM safe-DB + InstanceDBs.csv."""
        from pipeline4.core import config, run
        from pipeline4.domain import staging, datablocks
        from pipeline4.domain.blocks import engine
        self._emit("PHASE", "800 Software Generation  (820 Blocks + 830 Instances + 02_COM + 03 FC XML)")
        self._status("software…")
        findings = []
        database, f = staging.stage(); findings += f
        if not run.has_blocking(f):
            database, f = datablocks.build(database); findings += f
        if not self._gate(findings, label="800 (300 staging + 520 prereq)"):
            return
        if "db_blocks" not in database:
            self._emit("WARN", "  520 prereq produced no tables (a blocking finding was downgraded but yielded no data) - nothing further")
            return
        database, blk_findings = engine.build(database)
        res = engine.project(database)
        com = engine.write_com_db(database)
        inst = engine.write_instance_dbs(database)
        self._render(blk_findings + res["findings"])
        self._emit("PASS", f"  820: {len(database['software_blocks'])} block(s) -> {res['count']} "
                           f"CreationInfo CSV(s) + {len(res['xml_files'])} FC XML -> {config.blocks_creation_dir()}")
        if com["path"]:
            self._emit("PASS", f"  02_COM safe-DB: {com['members']} member(s) -> {com['path']}")
        self._emit("PASS", f"  830 InstanceDBs: {inst['count']} instance DB(s) -> {inst['path']}")

    def _run_reporting(self):
        """Phase 900: build the full SSOT (stage -> 520 -> 700; then the WARN-only 400/600/800) then
        coverage.build (the coverage table + ORPHAN/UNPLACED findings) -> coverage.project (the reports)."""
        from pipeline4.core import config, run
        from pipeline4.domain import staging, datablocks, interfaces, diagnosis, hardware, coverage
        from pipeline4.domain.blocks import engine
        self._emit("PHASE", "900 Reporting  (910 Pipeline Coverage)")
        self._status("coverage…")
        findings = []
        database, f = staging.stage(); findings += f
        if not run.has_blocking(findings):
            database, f = datablocks.build(database); findings += f
        if not run.has_blocking(findings):
            database, f = hardware.build(database); findings += f
        if not self._gate(findings, label="900 (300 + 520 + 700 prereqs)"):
            return
        if "db_blocks" not in database:
            self._emit("WARN", "  a blocking prereq was downgraded but yielded no data - nothing further")
            return
        proj = []
        database, fi = interfaces.build_interfaces(database); proj += fi
        database, fd = diagnosis.build(database); proj += fd
        database, fb = engine.build(database); proj += fb
        database, fc = coverage.build(database); proj += fc
        res = coverage.project(database)
        self._render(proj)
        st = res["stats"]
        self._emit("PASS", f"  910 coverage: {st['rows']} rows (sig {st['kinds']['signal']}/"
                           f"chan {st['kinds']['channel']}/struct {st['kinds']['structural']}), "
                           f"{st['orphans']} ORPHAN, {st['unplaced']} UNPLACED -> {res['txt']}")

    # --- chrome ---------------------------------------------------------------------------------- #
    def _on_levels_changed(self) -> None:
        """A Levels-dropdown toggle: apply the shown set live + persist it to app_config.yaml (FAIL/ERROR
        are always included)."""
        levels = {level for level, var in self._level_vars.items() if var.get()}
        self.log.set_shown_levels(levels)
        config.save_app_log_levels(levels)

    def _toggle_theme(self):
        self.mode = "light" if self.mode == "dark" else "dark"
        backend = theme.apply_theme(self.root, self.mode)
        self._backend_label.configure(text=f"theme: {backend}")
        self.log.append("INFO", f"theme -> {self.mode}")

    def _clear(self):
        self.log.clear()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()
