"""The PL4 operator window: a toolbar, the phase-button bar, and a log viewer.

The backend isn't ported yet, so this is the testable SHELL the user asked for early (gui-less PL3 builds
hid integration problems until the GUI landed late). Phase buttons are wired to the log - clicking one
logs a line - so the plumbing (button -> handler -> log) is exercised now and each phase is wired into
this same hook as it gets ported. It launches even with no theme package and survives a button that does
nothing (`_on_phase` is wrapped so a future not-yet-ready handler can't take the window down).
"""
from __future__ import annotations

import os
import tkinter as tk
import traceback
from tkinter import ttk

from pipeline4.core import config
from pipeline4.gui import theme
from pipeline4.gui.logview import LogView
from pipeline4.gui.phasebar import PhaseBar

APP_TITLE = "Pipeline4 - SSOT database build (testing shell)"


class App:
    def __init__(self, root):
        self.root = root
        self.mode = "dark"
        root.title(APP_TITLE)
        root.geometry("1180x720")
        backend = theme.apply_theme(root, self.mode)

        toolbar = ttk.Frame(root)
        toolbar.pack(side="top", fill="x", padx=8, pady=(8, 4))
        ttk.Label(toolbar, text="PIPELINE4", font=("Consolas", 13, "bold")).pack(side="left", padx=(2, 14))
        ttk.Button(toolbar, text="Theme", command=self._toggle_theme).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Clear Log", command=self._clear).pack(side="left", padx=2)
        self._backend_label = ttk.Label(toolbar, text=f"theme: {backend}")
        self._backend_label.pack(side="right", padx=2)

        self.phasebar = PhaseBar(root, self._on_phase)
        self.phasebar.pack(side="top", fill="x", padx=8, pady=2)

        self.log = LogView(root, shown_levels=config.load_app_ui()["log_levels"])
        self.log.pack(side="top", fill="both", expand=True, padx=8, pady=6)

        self.status = ttk.Label(root, text="Ready", anchor="w", relief="sunken")
        self.status.pack(side="bottom", fill="x")

        self.log.append("PHASE", "Pipeline4 - SSOT database build (testing shell)")
        self.log.append("INFO", f"theme backend: {backend}")
        self.log.append("INFO", "The backend isn't wired yet - phase buttons just log. We are testing the GUI.")

    def _on_phase(self, number, label):
        try:
            if number == 300:
                self._run_staging()
            elif number == 400:
                self._run_interfaces()
            elif number == 500:
                self._run_data_blocks()
            elif number == 600:
                self._run_diagnosis()
            elif number == 700:
                self._run_hardware()
            elif number == 800:
                self._run_software()
            elif number == 0:
                self.log.append("PHASE", "Run Pipeline (all phases)")
                self.log.append("WARN", "  -> full run not wired yet")
            else:
                self.log.append("PHASE", f"{number} {label}")
                self.log.append("WARN", f"  -> phase {number} not implemented yet")
            self.status.configure(text=f"clicked: {label}")
        except Exception:  # noqa: BLE001  - a not-yet-ready handler must never take the window down
            self.log.append("ERROR", f"handler for {label} crashed:\n{traceback.format_exc()}")

    def _run_staging(self):
        """Phase 300 (wired): read the configured I/O List -> the signals table -> Database/signals.csv.
        Runs inline for now (a few seconds on a real workbook); a worker thread comes with the engine."""
        from pipeline4.core import config, run
        from pipeline4.domain import staging
        self.log.append("PHASE", "300 Documents Staging")
        self.status.configure(text="staging…")
        self.root.update_idletasks()
        database, findings = staging.stage()
        if not run.gate(findings, self.log.append, label="300 Documents Staging"):
            return
        signals = database["signals"]
        self.log.append("PASS", f"  staged {len(signals)} signals -> {os.path.join(config.database_dir(), 'signals.csv')}")

    def _run_data_blocks(self):
        """Phase 500 (wired): stage -> 520 the registry generates db_members + db_blocks + instance_dbs
        (+ writes back name_in_db/datablocks/plc_binding) -> project the GlobalDB XML; then 510 builds the
        interface tables and projects the consolidated PLCTags.xlsx. Runs inline for now."""
        from pipeline4.core import config, run
        from pipeline4.domain import staging, datablocks, datablock_xml, interfaces, io_tags
        self.log.append("PHASE", "500 Signals Mapping  (520 Data Blocks + 510 I/O Tags)")
        self.status.configure(text="data blocks…")
        self.root.update_idletasks()
        findings = []
        database, f = staging.stage(); findings += f                 # 300 staging
        if not run.has_blocking(f):
            database, f = datablocks.build(database); findings += f   # 520 data blocks
        if not run.gate(findings, self.log.append, label="500 (300 staging + 520 data blocks)"):
            return
        if "db_blocks" not in database:                              # a prereq FAIL was downgraded, but 520 never ran
            self.log.append("WARN", "  520 produced no tables (a blocking prereq was downgraded but yielded no data) - nothing further")
            return
        n_dbs, n_members = len(database["db_blocks"]), len(database["db_members"])
        self.log.append("PASS", f"  {n_members} db_members across {n_dbs} DBs (+ {len(database['instance_dbs'])} "
                                f"instance DBs) -> {os.path.join(config.database_dir(), 'db_members.csv')}")
        count = datablock_xml.project(database)
        self.log.append("PASS", f"  projected {count} GlobalDB XML(s) -> {config.blocks_import_dir()}")
        # 510 I/O Tags - build the interface tables (so interface tags are included) then project PLCTags.xlsx
        self.status.configure(text="I/O tags…")
        self.root.update_idletasks()
        database, iface_findings = interfaces.build_interfaces(database)   # 400 (WARN-only)
        res = io_tags.project(database)                                    # 510 (WARN-only)
        run.render(iface_findings + res["findings"], self.log.append)      # projections already written -> render, don't halt
        self.log.append("PASS", f"  510: {res['total']} I/O tags ({res['io_count']} signal + "
                                f"{res['iface_count']} interface) across {len(res['tables'])} tables -> "
                                f"{config.io_tags_dir()}")

    def _run_interfaces(self):
        """Phase 400 (wired through 400e): stage -> 520 -> the interfaces/interface_elements tables ->
        the IF_*.xlsx projection -> (gated) insert each as an IF_ sheet into the I/O List. 510 tags TODO."""
        from pipeline4.core import config, run
        from pipeline4.domain import staging, datablocks, interfaces, interface_xlsx
        self.log.append("PHASE", "400 Interfaces Generation")
        self.status.configure(text="interfaces…")
        self.root.update_idletasks()
        findings = []
        database, f = staging.stage(); findings += f                 # 300 staging
        if not run.has_blocking(f):
            database, f = datablocks.build(database); findings += f   # 520 prereq
        if not run.gate(findings, self.log.append, label="400 (300 staging + 520 prereq)"):
            return
        if "db_blocks" not in database:                              # a prereq FAIL was downgraded, but 520 never ran
            self.log.append("WARN", "  520 prereq produced no tables (a blocking finding was downgraded but yielded no data) - nothing further")
            return
        database, iface_findings = interfaces.build_interfaces(database)   # 400 (WARN-only)
        run.render(iface_findings, self.log.append)
        result = interface_xlsx.project(database)
        n_if, n_el = len(database["interfaces"]), len(database["interface_elements"])
        self.log.append("PASS", f"  {n_if} interfaces, {n_el} mirrored elements -> {len(result['created'])} "
                                f"IF_*.xlsx in {config.interfaces_dir()}")
        params = config.load_params()
        if config.get_param(params, "iolist_params.insert_interface_sheets", False):
            self.status.configure(text="inserting IF_ sheets…")
            self.root.update_idletasks()
            for action in interface_xlsx.insert_interface_sheets(database, iolist_path=params.get("iolist_path")):
                self.log.append("WARN" if action.startswith("[WARN]") else "INFO", f"  {action}")
        else:
            self.log.append("INFO", "  insert_interface_sheets: disabled (iolist_params.insert_interface_sheets)")

    def _run_diagnosis(self):
        """Phase 600 (wired): stage -> 520 build (plc_binding) -> diagnosis.build (the unified
        diagnosis_entries table) -> 610 project DiagList_IO/Logic.csv -> 620 project the OPC SCL."""
        from pipeline4.core import config, run
        from pipeline4.domain import staging, datablocks, diagnosis, diaglist_csv, diagnosis_scl
        self.log.append("PHASE", "600 Diagnosis Mapping  (610 DiagList + 620 OPC SCL)")
        self.status.configure(text="diagnosis…")
        self.root.update_idletasks()
        findings = []
        database, f = staging.stage(); findings += f                 # 300 staging
        if not run.has_blocking(f):
            database, f = datablocks.build(database); findings += f   # 520 prereq -> plc_binding write-back
        if not run.gate(findings, self.log.append, label="600 (300 staging + 520 prereq)"):
            return
        if "db_blocks" not in database:                              # a prereq FAIL was downgraded, but 520 never ran
            self.log.append("WARN", "  520 prereq produced no tables (a blocking finding was downgraded but yielded no data) - nothing further")
            return
        database, diag_findings = diagnosis.build(database)          # 600 builder (records, saves)
        res = diaglist_csv.project(database)                         # 610 projection
        scl = diagnosis_scl.project(database)                        # 620 projection
        run.render(diag_findings + res["findings"] + scl["findings"], self.log.append)   # WARN-only -> render
        self.log.append("PASS", f"  610 DiagList: {res['io_count']} IO + {res['logic_count']} logic rows -> "
                                f"{config.diaglist_dir()}")
        if scl["path"]:
            self.log.append("PASS", f"  620 OPC SCL: {scl['entries']} entries across {scl['cabinets']} "
                                    f"cabinets -> {scl['path']}")

    def _run_hardware(self):
        """Phase 700 (wired): stage -> hardware.build (the hardware_stations + hardware_modules tables) ->
        hardware_csv.project (the format-2 Stations.csv + Modules.csv). Hardware needs only staging (300)."""
        from pipeline4.core import config, run
        from pipeline4.domain import staging, hardware, hardware_csv
        self.log.append("PHASE", "700 Hardware Generation  (710 Stations + 720 Modules)")
        self.status.configure(text="hardware…")
        self.root.update_idletasks()
        findings = []
        database, f = staging.stage(); findings += f                 # 300 staging
        if not run.has_blocking(f):
            database, f = hardware.build(database); findings += f     # 700 hardware build (halt-capable)
        if not run.gate(findings, self.log.append, label="700 (300 staging + hardware)"):
            return
        if "hardware_stations" not in database:                      # a blocking finding -> build wrote nothing
            self.log.append("WARN", "  700 produced no tables (a blocking finding) - nothing further")
            return
        res = hardware_csv.project(database)
        self.log.append("PASS", f"  700: {res['stations']} station(s) + {res['modules']} module(s) -> "
                                f"{config.hardware_dir()}")

    def _run_software(self):
        """Phase 800 (wired): stage -> 520 build (the write-back fields the builders read) -> 800 build
        (the software_blocks/software_block_members tables) -> project (the CreationInfo CSVs + the 03 FC
        XML, dropping 03's CSV) -> write the 02_COM safe-DB + InstanceDBs.csv. Software depends on 520."""
        from pipeline4.core import config, run
        from pipeline4.domain import staging, datablocks
        from pipeline4.domain.blocks import engine
        self.log.append("PHASE", "800 Software Generation  (820 Blocks + 830 Instances + 02_COM + 03 FC XML)")
        self.status.configure(text="software…")
        self.root.update_idletasks()
        findings = []
        database, f = staging.stage(); findings += f                 # 300 staging
        if not run.has_blocking(f):
            database, f = datablocks.build(database); findings += f   # 520 prereq -> write-back fields
        if not run.gate(findings, self.log.append, label="800 (300 staging + 520 prereq)"):
            return
        if "db_blocks" not in database:                              # a prereq FAIL was downgraded, but 520 never ran
            self.log.append("WARN", "  520 prereq produced no tables (a blocking finding was downgraded but yielded no data) - nothing further")
            return
        database, blk_findings = engine.build(database)              # 800 SSOT build (WARN-only, records+saves)
        res = engine.project(database)                               # CreationInfo CSVs + 03 FC XML (CSV dropped)
        com = engine.write_com_db(database)                          # the 02_COM safe-DB
        inst = engine.write_instance_dbs(database)                   # InstanceDBs.csv
        run.render(blk_findings + res["findings"], self.log.append)  # WARN-only -> render (output already written)
        self.log.append("PASS", f"  820: {len(database['software_blocks'])} block(s) -> {res['count']} "
                                f"CreationInfo CSV(s) + {len(res['xml_files'])} FC XML -> {config.blocks_creation_dir()}")
        if com["path"]:
            self.log.append("PASS", f"  02_COM safe-DB: {com['members']} member(s) -> {com['path']}")
        self.log.append("PASS", f"  830 InstanceDBs: {inst['count']} instance DB(s) -> {inst['path']}")

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
