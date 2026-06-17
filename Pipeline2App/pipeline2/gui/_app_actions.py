#!/usr/bin/env python3
"""_app_actions.py - the run/worker half of pipeline2.gui.gui.App.

`ActionsMixin` holds the per-phase pipeline methods (`_phase_*`), the tooling
workers (`_work_*`), the run actions (`_on_run*`, `_start`, `_guard`), the
worker-thread emit helpers (`_log`, `_log_line`, `_section`, `_stat`) and the
`_PHASE_FN` dispatch table.  It is mixed into `App` in gui.py; every method here
runs as a method of `App` and uses `self.*`, so the split is purely cosmetic
(no behaviour change).  The shared module-level names and the gui-local helpers
are imported from `pipeline2.gui.gui`, which is already fully populated by the
time gui.py pulls this mixin in.
"""
from __future__ import annotations
import importlib
import os
import re
import threading
import traceback

from pipeline2.core import config, staging, outputs, hardware
from pipeline2.core import i18n  # noqa: F401  (kept for parity with the original namespace)
from pipeline2.core import error_management, validation
from pipeline2.interfaces import interface_tool
from pipeline2.gui import gui_common
from pipeline2.gui import project
from pipeline2.blocks import block_templates
from pipeline2.blocks import block_builders
from pipeline2.blocks import softwareblocks
from pipeline2.blocks import blockshells
from pipeline2.interfaces import verify

# gui-local names (helpers + constants) - gui.py defines these before it imports
# this mixin, so the import is resolved against the partially-initialised module.
from pipeline2.gui.gui import PHASES, _abs


class ActionsMixin:
    # ---- cascade run trigger ------------------------------------------- #
    def _run_validation_phases(self, phase_set):
        self._start(lambda: self._phase_validation(set(phase_set)))

    # ---- block-tooling workers ----------------------------------------- #
    def _work_shells(self):
        self._section("BLOCK SHELLS  (per-template shell sheets -> SoftwareBlocks.xlsm)")
        self._reload_builders()
        params = config.load_params()
        types = config.load_signal_types()
        db, _w = staging.load_io_list(params, types)
        r = blockshells.generate_shells(db)
        self._log("OK", f"+{r['created']} shell(s) created, {r['kept']} kept  ->  {os.path.basename(r['path'])}")
        self._log("INFO", "  set each sheet's directive (B2) to keep / fill / override")
        self._stat("block shells generated")

    def _work_softwareblocks(self):
        self._section("SOFTWARE BLOCKS  (block_builders / shell -> SoftwareBlocksBuilder CSV)")
        self._reload_builders()
        for stem, (path, n, mode) in softwareblocks.generate().items():
            self._log("OK", f"{n} instance(s)  [{mode}]  ->  {os.path.basename(path)}")
        self._stat("SoftwareBlocks CSV generated")

    def _work_coverage(self):
        self._section("COVERAGE  (every signal lands somewhere)")
        self._reload_builders()
        s = verify.generate()
        self._log("OK" if s["orphans"] == 0 else "WARNING",
                  f"{s['covered']}/{s['total']} covered, {s['orphans']} orphan(s), "
                  f"{s['unplaced']} unplaced member(s), {s['untyped']} untyped/spare")
        self._log("INFO", "  -> Reports/io_project_coverage_report.csv + .txt")
        self._stat("coverage report written")

    def _work_scan_templates(self):
        self._section("BLOCK TEMPLATES  (scan !!key$$ -> json -> sync block_builders.py)")
        s = block_templates.build_templates_json()
        self._log("OK", f"+{s['added_templates']} template(s), +{s['added_keys']} new key(s), "
                         f"{s['kept_keys']} kept binding(s)  ->  config_project/block_templates.json")
        for m in s["missing"]:
            self._log("INFO", f"  key no longer in template (kept): {m}")
        b = block_templates.sync_builders()
        self._log("OK", f"block_builders.py: {b['kept']} kept ($keep), {b['replaced']} re-stubbed "
                         f"($replace), {b['added']} added")
        importlib.reload(block_builders)  # pick up the regenerated builders
        self._stat("templates scanned + builders synced")

    def _reload_builders(self):
        """Re-import block_builders.py so the latest edits are used by the runs."""
        importlib.reload(block_builders)

    def _work_export_central(self):
        self._section("CENTRAL DATABASE  (staged rows -> InformationDatabase/IODatabase.csv)")
        self._stat("exporting Central Database ...")
        path = block_templates.dump_staged()
        self._log("OK", f"{os.path.basename(path)} written  ->  {path}")
        self._stat("IODatabase.csv exported")

    # ---- run actions (spawn worker) ------------------------------------ #
    def _on_run_all(self):
        self._start(self._work_run_all)

    def _on_run_phase(self, name: str):
        self._start(lambda: self._work_phase(name))

    def _start(self, target):
        if self.busy:
            return
        self.q.put(("busy", True))
        threading.Thread(target=self._guard(target), daemon=True).start()

    def _guard(self, target):
        def wrapped():
            try:
                target()
            except Exception as e:  # noqa: BLE001
                self._log("ERROR", f"aborted: {e}", None)
                self._log("INFO", traceback.format_exc().strip().splitlines()[-1], None)
            finally:
                self.q.put(("busy", False))
        return wrapped

    # ---- worker-thread emit helpers ------------------------------------ #
    def _log(self, level, text, link=None):
        self.q.put(("log", level, text, link))

    def _log_line(self, level, location, body, link1=None, link2=None):
        """A structured validation line (leading clickable cell + aligned comparison body + link2)."""
        self.q.put(("logline", level, location, body, link1, link2))

    def _section(self, title):
        self.q.put(("log", "SECTION", title, None))

    def _stat(self, text):
        self.q.put(("status", text))

    # ---- worker-thread pipeline ---------------------------------------- #
    def _out_dir(self) -> str:
        # an open project writes into <project>/Output; the bundled default keeps params.output_dir
        if os.path.abspath(self._project_path) != os.path.abspath(config.PARAMS_FILE):
            return os.path.join(project.project_dir(self._project_path), project.OUTPUT_DIR)
        try:
            return config.output_root(getattr(self, "_params", None) or config.load_params(self._project_path))
        except Exception:  # noqa: BLE001
            return config.OUTPUT_ROOT

    def _load_models(self):
        self._params = config.load_params(self._project_path)
        self._types = config.load_signal_types()
        self._dtd = config.load_device_types_db(self._params)

    def _ensure_staged(self):
        self._load_models()
        if self._rows is None:
            io_path = self._params["io_list"]["path"]
            if not os.path.exists(io_path):
                raise FileNotFoundError(f"I/O List not found: {io_path}")
            self._stat("staging - reading I/O List ...")
            self._rows, self._warns = staging.load_io_list(self._params, self._types)

    def _staging_link(self, warning: str):
        cm = re.search(r"column ([A-Z]+)", warning)
        if not cm:
            return None
        io = self._params["io_list"]
        sm = re.search(r"IoList\[([^\]]+)\]", warning)  # the sheet the warning is about
        sheets = config.as_sheet_list(io.get("sheet"))
        sheet = sm.group(1) if sm else (sheets[0] if sheets else "")
        return {"path": io["path"], "sheet": sheet, "cell": f"{cm.group(1)}{io['header_row']}"}

    def _phase_staging(self):
        self._section("STAGING  (reading the I/O List)")
        self._ensure_staged()
        self._log("OK", f"{len(self._rows)} row(s) loaded")
        for w in self._warns:
            is_warn = ("header" in w and "!=" in w)
            self._log("WARNING" if is_warn else "INFO", w, self._staging_link(w) if is_warn else None)

    def _phase_validation(self, phases=None):
        self._section("VALIDATION  (C&E / AREA + diagnosis bit map vs I/O List)")
        self._ensure_staged()
        ce = self._params["ce"]
        if not os.path.exists(ce["path"]):
            self._log("WARNING", f"C&E document not found - C&E/AREA checks skipped: {ce['path']}")
        self._stat("validating ...")
        out = self._out_dir()
        log = validation.validate(self._params, self._rows, phases=phases, lang=self._lang, out_dir=out)
        passed, failed, warned = validation.write_log(log, out)
        skipped = sum(1 for e in log if e.level == "SKIP")
        full_print = bool(self._params.get("ce_full_print"))
        self.q.put(("errlink", os.path.join(config.USER_INPUT, error_management.CSV_NAME)))   # [FAIL] -> registry
        self._log("OK" if failed == 0 else "WARNING",
                  f"{passed} passed, {failed} failed, {warned} warning(s), {skipped} skipped  ->  OutputTree/Reports/documents_validation_report.txt")
        # FAIL/WARN always; with ce_full_print also the passed/skipped/info rows (greyed). The
        # aligned caller-vs-other table + filter + links all live in validation.render_lines.
        full_print = bool(self._params.get("ce_full_print"))
        gui_common.render_validation_log(self._section, self._log_line, log,
                                         full_print=full_print, ce_path=ce["path"])

    def _phase_iotags(self):
        self._section("I/O TAGS")
        self._ensure_staged()
        tables = outputs.build_io_tags(self._rows)
        n = outputs.write_io_tags(tables, self._out_dir())
        self._log("OK", f"{n} tag(s) across {len(tables)} table(s)  ->  PlcTags/PLCTags.xlsx")

    def _phase_dbs(self):
        self._section("DATA BLOCKS")
        self._ensure_staged()
        dbs = outputs.build_dbs(self._rows, self._types)
        n = outputs.write_dbs(dbs, self._out_dir())
        self._log("OK", f"{n} DB(s)  ->  SoftwareBlocks/ImportReady")
        for name, db in sorted(dbs.items()):
            kind = "safe" if db["kind"] == "safe_db" else "std"
            self._log("INFO", f"  {name}  ({kind}, {len(db['members'])} member(s))")

    def _phase_diagnosis(self):
        self._section("DIAGNOSIS  (List_IO + List_Logic + OPC SCL)")
        self._ensure_staged()
        from pipeline2.diagnosis import diagnostic_opc
        d = diagnostic_opc.generate_for(self._rows, config.load_params(), self._out_dir())
        self._log("OK", f"{d['io']} List_IO + {d['logic']} List_Logic row(s)  ->  DiagnosisData/")
        self._log("OK", f"SCL  ->  SoftwareBlocks/ImportReady/{os.path.basename(d['scl'])}")

    def _phase_hardware(self):
        self._section("HARDWARE  (Stations / Modules, format 2)")
        self._ensure_staged()
        stations, modules, messages = hardware.extract(self._rows, self._dtd)
        nst = hardware.write_stations(stations, self._out_dir())
        nmod = hardware.write_modules(modules, self._out_dir())
        self._log("OK", f"{nst} station(s), {nmod} module(s)  ->  HardwareConfiguration")
        io = self._params["io_list"]
        sheets = config.as_sheet_list(io.get("sheet"))
        default_sheet = sheets[0] if sheets else ""
        for level, text in messages:
            sm = re.search(r"\[([^\]]+)\] row (\d+)", text)   # "[sheet] row N ..."
            rm = re.search(r"row (\d+)", text)
            if sm:
                sheet, n = sm.group(1), sm.group(2)
            elif rm:
                sheet, n = default_sheet, rm.group(1)
            else:
                sheet = n = None
            link = {"path": io["path"], "sheet": sheet, "cell": f"A{n}"} if n else None
            self._log(level, text, link)

    def _phase_interfaces(self):
        self._section("INTERFACES  (IOC rows)")
        self._load_models()
        io = self._params["io_list"]
        tpl = _abs(self._params.get("interface_template", "Templates/TEMPLATE_INTERFACES_v0.0.xlsx"))
        if not os.path.exists(tpl):
            self._log("WARNING", f"interface template not found - skipped: {tpl}")
            return
        self._stat("generating interfaces ...")
        n = interface_tool.generate(io["path"], io["sheet"], io["header_row"],
                                    config.out_path(self._out_dir(), "interfaces_dir"), tpl)
        self._log("OK", f"{n} interface file(s) created (existing preserved)  ->  Interfaces")

    _PHASE_FN = {
        "Staging": "_phase_staging", "Validation": "_phase_validation",
        "I/O Tags": "_phase_iotags", "DBs": "_phase_dbs", "Diagnosis": "_phase_diagnosis",
        "Hardware": "_phase_hardware", "Interfaces": "_phase_interfaces",
    }

    def _work_phase(self, name: str):
        getattr(self, self._PHASE_FN[name])()
        self._stat(f"{name} done")

    def _work_run_all(self):
        self._rows = None  # always start from a fresh stage
        for name in PHASES:
            getattr(self, self._PHASE_FN[name])()
        self._section("DONE")
        self._log("OK", f"pipeline complete  ->  {self._out_dir()}")
        self._stat("Run All done")

    # ---- misc ----------------------------------------------------------- #
    def _open_output(self):
        out = self._out_dir()
        os.makedirs(out, exist_ok=True)
        self._open_path(out)
