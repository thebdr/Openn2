"""Run the active system's Run-all plan HEADLESS - the phase buttons without the window.

Chapter: generating a handoff workspace from a shell (a CI job, the OP5 verification, a quick regeneration
of the builtin Shared/OutputTree). The same dispatch the App performs - every run_plan phase through
`HANDLERS[phase.handler](ctx)` with the App's gate semantics (the treatments registry applied, a blocking
finding halts the chain) - the log printed to the console instead of the log panel, over the builtin config
(`Shared/`: the Database and the Output tree) or a project folder. ONE generation id for the whole chain
(what the Siemens handoff stamps as the contract-v1 `run` - Shared/PL5_OP5_contract.md §6.2); `--phase`
runs one phase under its own id, exactly like its button.

The one document-WRITING leg inside the run plan - the 400 insert of the IF_ sheets into the I/O List - is
OFF unless `--insert-sheets` says so (the byte-parity oracle and the handler tests skip it the same way): a
headless regeneration must not rewrite the source document, builtin fixture included.

Run:   <python> scripts/run_pipeline.py                  (the builtin config -> Shared/OutputTree)
       <python> scripts/run_pipeline.py --project <dir>  (a project folder -> <dir>/Output)
       <python> scripts/run_pipeline.py --phase 700      (one phase number of the plan)
The exit code is the verdict: 0 = the chain completed, 1 = halted on a blocking finding / crashed.
"""
from __future__ import annotations

import argparse
import datetime
import os
import secrets
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
PL5_ROOT = os.path.dirname(HERE)
sys.path.insert(0, PL5_ROOT)

_ISSUES = ("FAIL", "ERRR", "WARN")


class ConsoleHost:
    """The App's seams, printing: the log lines, the gate (the treatments registry applied; an effective
    FAIL halts the chain - the severity contract), the render (no halt unless effective FAIL)."""

    def __init__(self):
        self.halted = False

    def ctx(self, system, run: str):
        from pipeline5.systems.system_contract import PhaseContext
        return PhaseContext(system=system, emit=self.emit, status=lambda _text: None, gate=self.gate,
                            render=self.render, records=self.records, halt=self.halt, lang="en", run=run)

    @staticmethod
    def emit(level: str, message: str) -> None:
        print(f"[{level}] {message}")

    @staticmethod
    def _apply(findings, label: str) -> list:
        """[(finding, effective severity)] with the registry applied; the issues printed."""
        from pipeline5.findings import treatments
        applied = treatments.apply(findings, treatments.load())
        for finding, effective in applied:
            if effective in _ISSUES:
                print(f"[{effective}] {label}: {finding.type} - {finding.detail}  @ {finding.location}")
        return applied

    def gate(self, findings, label: str = "") -> bool:
        from pipeline5.findings import treatments
        if treatments.should_halt(self._apply(findings, label)):
            self.halted = True
            return False
        return True

    def render(self, findings, label: str = "") -> None:
        from pipeline5.findings import treatments
        if treatments.should_halt(self._apply(findings, label)):
            self.halted = True

    @staticmethod
    def records(records) -> None:
        for record in records:
            print(f"  {getattr(record, 'text', record)}")

    def halt(self) -> None:
        self.halted = True


def generation_id() -> str:
    """One id per chain / per `--phase` call - the same form the App mints per button press."""
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2)


def _keep_documents_untouched() -> None:
    """Force `iolist_params.insert_interface_sheets` OFF for this process - the handler tests' sandbox rule."""
    from pipeline5 import config
    original = config.load_params

    def load_params(path=None):
        params = original(path)
        section = params.get("iolist_params")
        if isinstance(section, dict):
            section["insert_interface_sheets"] = False
        return params
    config.load_params = load_params


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run the pipeline's Run-all plan (or one phase) headless.")
    parser.add_argument("--project", default="", help="a project folder (default: the builtin config + Shared/)")
    parser.add_argument("--phase", type=int, default=0, help="run ONE phase number of the plan instead of the chain")
    parser.add_argument("--insert-sheets", action="store_true",
                        help="let phase 400 insert the IF_ sheets into the I/O List (writes the source document)")
    args = parser.parse_args(argv)

    from pipeline5 import config
    from pipeline5.systems import catalog
    if args.project:
        from pipeline5.project import project_manager as project
        root = project.open_project(os.path.abspath(args.project))
        systems = project.project_systems(root)
        system = systems[0] if systems else catalog.by_id("siemens_s7_safety")
    else:
        system = catalog.by_id("siemens_s7_safety")
    config.use_system(system)
    if not args.insert_sheets:
        _keep_documents_untouched()

    run = generation_id()
    host = ConsoleHost()
    numbers = [args.phase] if args.phase else list(system.phases.run_order())
    print(f"=== {system.id}: {'phase ' + str(args.phase) if args.phase else 'Run-all'}  (run {run}) "
          f"-> {config.output_root()}")
    for number in numbers:
        phase = system.phases.by_number(number)
        if phase is None or not phase.handler:
            print(f"=== phase {number} is not runnable")
            return 1
        try:
            system.handlers[phase.handler](host.ctx(system, run))
        except Exception:  # noqa: BLE001 - attribute the crash to the phase, like the App does
            traceback.print_exc()
            print(f"=== {number} crashed - the chain is aborted")
            return 1
        if host.halted:
            print(f"=== halted at {number} on a blocking finding - the remaining phases are skipped")
            return 1
    print("=== complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
