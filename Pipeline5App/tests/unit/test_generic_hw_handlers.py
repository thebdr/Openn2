"""The generic-hardware systems' handlers, HEADLESS, on the fixture I/O List (the Siemens harness's seams):
each run_plan phase of each type runs through System.handlers[phase.handler](ctx) with a fresh host, emits a
RSLT line, and - the TIA type on the PLC-based fixture, the SYCON type on the same list - produces its hardware
tables where its OutputLayout says. Validation (110 only) judges the fixture with the type's mandatory columns.
Sandboxed like test_siemens_main_handlers: Database/Output into temp dirs, the treatments registry copied."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile

from _harness import run, eq, ok
from pipeline5 import config
from pipeline5.config import paths as p5paths
from pipeline5.findings import treatments
from pipeline5.systems.ipc_based.hilscher_syconnet.generic_hw.system import SYSTEM as SYCON
from pipeline5.systems.plc_based.siemens_s7.generic_hw.system import SYSTEM as TIA
from pipeline5.systems.system_contract import PhaseContext


class _Host:
    def __init__(self, system):
        self.system, self.lines, self.rendered, self.halted = system, [], [], False

    def ctx(self):
        return PhaseContext(system=self.system, emit=lambda level, msg: self.lines.append((level, msg)),
                            status=lambda _t: None, gate=self._gate, render=self._render,
                            records=lambda recs: self.rendered.append(list(recs)), halt=self._halt, lang="en", run="")

    def _apply(self, findings):
        self.rendered.append(list(findings))
        return treatments.apply(findings, treatments.load())

    def _gate(self, findings, label=""):
        if treatments.should_halt(self._apply(findings)):
            self.halted = True
            return False
        return True

    def _render(self, findings, label=""):
        if treatments.should_halt(self._apply(findings)):
            self.halted = True

    def _halt(self):
        self.halted = True

    def levels(self):
        return [level for level, _ in self.lines]


def _sandboxed(fn):
    def wrapped():
        orig_db, orig_out = p5paths._BUILTIN_DATABASE, p5paths._BUILTIN_OUTPUT
        orig_registry, orig_load_params, orig_system = treatments.registry_path, config.load_params, p5paths._ACTIVE_SYSTEM
        with tempfile.TemporaryDirectory() as db_dir, tempfile.TemporaryDirectory() as out_dir:
            registry_copy = os.path.join(db_dir, "finding_treatments.csv")
            if os.path.isfile(orig_registry()):
                shutil.copy2(orig_registry(), registry_copy)

            def load_params_no_insert(path=None):
                params = orig_load_params(path)
                section = params.get("iolist_params")
                if isinstance(section, dict):
                    section["insert_interface_sheets"] = False
                return params

            p5paths._BUILTIN_DATABASE, p5paths._BUILTIN_OUTPUT = db_dir, out_dir
            treatments.registry_path = lambda: registry_copy
            config.load_params = load_params_no_insert
            try:
                fn(out_dir)
            finally:
                p5paths._BUILTIN_DATABASE, p5paths._BUILTIN_OUTPUT = orig_db, orig_out
                treatments.registry_path = orig_registry
                config.load_params = orig_load_params
                p5paths._ACTIVE_SYSTEM = orig_system          # the resolver's own tuple, put back as found
                p5paths._refresh_address_format()
    return wrapped


def _run_plan(system):
    hosts = {}
    config.use_system(system)
    for number in system.phases.run_order():
        phase = system.phases.by_number(number)
        host = _Host(system)
        system.handlers[phase.handler](host.ctx())
        ok("RSLT" in host.levels() or host.halted, f"{system.id} phase {number}: a RSLT line or a halt (got {host.levels()})")
        hosts[number] = host
    return hosts


@_sandboxed
def test_tia_generic_hw_run_plan(out_dir):
    hosts = _run_plan(TIA)
    eq(hosts[100].halted, False, "the fixture passes the 110 checks with the TIA type's mandatory columns")
    eq(hosts[700].halted, False, "the TIA hardware build does not halt on the fixture")
    rslt = [m for lvl, m in hosts[700].lines if lvl == "RSLT"]
    ok(rslt and "stations" in rslt[-1] and "modules" in rslt[-1], rslt)
    hw = TIA.output_layout.dirs()["hardware"]
    ok(os.path.isfile(os.path.join(hw, "Stations.csv")) and os.path.isfile(os.path.join(hw, "Modules.csv")),
       "hw/stations + hw/modules written into the OP5 workspace")


@_sandboxed
def test_sycon_generic_hw_run_plan(out_dir):
    hosts = _run_plan(SYCON)
    eq(hosts[100].halted, False, "the fixture passes the 110 checks with the SYCON type's mandatory columns")
    hw = SYCON.output_layout.dirs()["hardware"]
    ok(hw.startswith(out_dir), "the handoff folder lies under the sandboxed output root")
    for name in ("SyconStations.csv", "SyconModules.csv", "SyconDeviceTypesDatabase.csv"):
        ok(os.path.isfile(os.path.join(hw, name)), f"{name} written")
    rslt = [m for lvl, m in hosts[700].lines if lvl == "RSLT"]
    ok(rslt and "stations" in rslt[-1], rslt)


@_sandboxed
def test_generic_validation_sub_110_logs_only(out_dir):
    config.use_system(TIA)
    host = _Host(TIA)
    TIA.handlers["validation"](host.ctx(), only=110)
    ok(any("110:" in m for lvl, m in host.lines if lvl == "RSLT"), host.lines)
    ok(not os.listdir(config.validation_report_dir()) if os.path.isdir(config.validation_report_dir()) else True,
       "a sub-phase run writes no report")


if __name__ == "__main__":
    sys.exit(run("generic_hw_handlers", [
        ("tia_generic_hw_run_plan", test_tia_generic_hw_run_plan),
        ("sycon_generic_hw_run_plan", test_sycon_generic_hw_run_plan),
        ("generic_validation_sub_110_logs_only", test_generic_validation_sub_110_logs_only),
    ]))
