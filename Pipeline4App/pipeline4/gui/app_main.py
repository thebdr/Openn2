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

        self.log = LogView(root)
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
        from pipeline4.core import config
        from pipeline4.domain import staging
        self.log.append("PHASE", "300 Documents Staging")
        self.status.configure(text="staging…")
        self.root.update_idletasks()
        database = staging.stage()
        signals = database["signals"]
        self.log.append("PASS", f"  staged {len(signals)} signals -> {os.path.join(config.database_dir(), 'signals.csv')}")
        dupes = signals.duplicate_uids()
        if dupes:
            self.log.append("WARN", f"  {len(dupes)} duplicate signal uid(s) - the key needs a tiebreak")

    def _run_data_blocks(self):
        """Phase 500 (wired): stage -> 520 the registry generates db_members + db_blocks + instance_dbs
        (+ writes back name_in_db/datablocks/plc_binding) -> project the GlobalDB XML; then 510 builds the
        interface tables and projects the consolidated PLCTags.xlsx. Runs inline for now."""
        from pipeline4.core import config
        from pipeline4.domain import staging, datablocks, datablock_xml, interfaces, io_tags
        self.log.append("PHASE", "500 Signals Mapping  (520 Data Blocks + 510 I/O Tags)")
        self.status.configure(text="data blocks…")
        self.root.update_idletasks()
        database = staging.stage()
        database, errors, warnings = datablocks.build(database)
        for w in warnings:
            self.log.append("WARN", f"  {w}")
        if errors:
            for e in errors:
                self.log.append("FAIL", f"  {e}")
            self.log.append("FAIL", "  520 halted on a config error - nothing written")
            return
        n_dbs, n_members = len(database["db_blocks"]), len(database["db_members"])
        self.log.append("PASS", f"  {n_members} db_members across {n_dbs} DBs (+ {len(database['instance_dbs'])} "
                                f"instance DBs) -> {os.path.join(config.database_dir(), 'db_members.csv')}")
        count = datablock_xml.project(database)
        self.log.append("PASS", f"  projected {count} GlobalDB XML(s) -> {config.blocks_import_dir()}")
        # 510 I/O Tags - build the interface tables (so interface tags are included) then project PLCTags.xlsx
        self.status.configure(text="I/O tags…")
        self.root.update_idletasks()
        database, iface_warnings = interfaces.build_interfaces(database)
        for w in iface_warnings[:20]:
            self.log.append("WARN", f"  {w}")
        res = io_tags.project(database)
        for w in res["warnings"]:
            self.log.append("WARN", f"  {w}")
        self.log.append("PASS", f"  510: {res['total']} I/O tags ({res['io_count']} signal + "
                                f"{res['iface_count']} interface) across {len(res['tables'])} tables -> "
                                f"{config.io_tags_dir()}")

    def _run_interfaces(self):
        """Phase 400 (wired through 400e): stage -> 520 -> the interfaces/interface_elements tables ->
        the IF_*.xlsx projection -> (gated) insert each as an IF_ sheet into the I/O List. 510 tags TODO."""
        from pipeline4.core import config
        from pipeline4.domain import staging, datablocks, interfaces, interface_xlsx
        self.log.append("PHASE", "400 Interfaces Generation")
        self.status.configure(text="interfaces…")
        self.root.update_idletasks()
        database = staging.stage()
        database, errors, _w = datablocks.build(database)
        if errors:
            for e in errors:
                self.log.append("FAIL", f"  520 (prereq): {e}")
            return
        database, warnings = interfaces.build_interfaces(database)
        for w in warnings[:20]:
            self.log.append("WARN", f"  {w}")
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
        from pipeline4.core import config
        from pipeline4.domain import staging, datablocks, diagnosis, diaglist_csv, diagnosis_scl
        self.log.append("PHASE", "600 Diagnosis Mapping  (610 DiagList + 620 OPC SCL)")
        self.status.configure(text="diagnosis…")
        self.root.update_idletasks()
        database = staging.stage()
        database, errors, _w = datablocks.build(database)        # 520 prereq -> plc_binding write-back
        if errors:
            for e in errors:
                self.log.append("FAIL", f"  520 (prereq): {e}")
            return
        database, errors, warnings = diagnosis.build(database)
        for w in warnings[:20]:
            self.log.append("WARN", f"  {w}")
        if errors:
            for e in errors:
                self.log.append("FAIL", f"  600 halted: {e}")
            return
        res = diaglist_csv.project(database)
        self.log.append("PASS", f"  610 DiagList: {res['io_count']} IO + {res['logic_count']} logic rows -> "
                                f"{config.diaglist_dir()}")
        scl = diagnosis_scl.project(database)
        for w in scl["warnings"]:
            self.log.append("WARN", f"  {w}")
        if scl["path"]:
            self.log.append("PASS", f"  620 OPC SCL: {scl['entries']} entries across {scl['cabinets']} "
                                    f"cabinets -> {scl['path']}")

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
