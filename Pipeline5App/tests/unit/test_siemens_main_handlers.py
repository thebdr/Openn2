"""The Siemens phase handlers (safety/main.py), run HEADLESS against the real fixture documents -
the phase buttons without Tk.

This is the step-5 payoff of the PhaseContext seam: every handler reports only through
`ctx.emit/status/gate/render/records/halt`, so the whole Run-all chain executes here with the
App's REAL gate semantics (treatments applied, halt on effective severity) - exactly the dispatch
the App performs, minus the window. It catches the bug class the byte-parity oracle CANNOT see:
the oracle drives the chain functions directly with hand-passed arguments, while THIS runs the
handlers' own wiring (the 900 handler shipped for a whole step calling `engine.build(database)`
without its system - a guaranteed click-time crash the oracle never noticed).

Sandboxed like the oracle (module-attr overrides for the Database/Output roots), the treatments
registry copied aside (run_validation reconciles it - the builtin file must not be rewritten by a
test), and - also like the oracle - the document-MUTATING legs stay off: the 200 fill / 245 risky
handlers are not in the run_plan, and the sandbox forces `insert_interface_sheets` OFF (the builtin
fixture config ships it ON for real operator runs; a test must not edit the repo's fixture doc).
The source document's mtime is asserted unchanged after the whole chain.
"""
import os
import shutil
import tempfile

from _harness import run, eq, ok
from pipeline5 import config
from pipeline5.config import paths as p5paths
from pipeline5.findings import treatments
from pipeline5.systems.plc_based.siemens_s7.safety import main
from pipeline5.systems.plc_based.siemens_s7.safety.system import SYSTEM
from pipeline5.systems.system_contract import PhaseContext


class _Host:
    """The App's seam wiring, as collectors: what `App._ctx()` hands a handler, minus Tk/queue.
    gate/render mirror App._gate/_render - the treatments registry is APPLIED and the halt flag
    follows the EFFECTIVE severity (the severity contract), not the raw one."""

    def __init__(self):
        self.lines = []            # every (level, message) a handler emitted
        self.rendered = []         # every findings/records batch handed to gate/render/records
        self.halted = False

    def ctx(self):
        return PhaseContext(
            system=SYSTEM,
            emit=lambda level, msg: self.lines.append((level, msg)),
            status=lambda _text: None,
            gate=self._gate,
            render=self._render,
            records=lambda recs: self.rendered.append(list(recs)),
            halt=self._halt,
            lang="en",
        )

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
    """The oracle's isolation, harness-side: Database/Output into temp dirs (module-attr overrides),
    the treatments registry copied into the sandbox (run_validation's reconcile must not rewrite the
    builtin file), and `insert_interface_sheets` forced OFF (the one doc-writing leg inside a
    run_plan handler - the oracle skips it too; the repo's fixture doc stays untouched)."""
    def wrapped():
        orig_db, orig_out = p5paths._BUILTIN_DATABASE, p5paths._BUILTIN_OUTPUT
        orig_registry = treatments.registry_path
        orig_load_params = config.load_params
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
                fn()
            finally:
                p5paths._BUILTIN_DATABASE, p5paths._BUILTIN_OUTPUT = orig_db, orig_out
                treatments.registry_path = orig_registry
                config.load_params = orig_load_params
    return wrapped


def test_run_plan_executes_end_to_end():
    """Every run_plan phase through HANDLERS[phase.handler](ctx), each with a fresh host (handlers
    are self-contained) - exactly the dispatch the App performs. Each handler must complete (a
    crash = red), report a RSLT line (the success marker - a silent no-op handler is a bug), and
    NEVER halt on the clean fixture.

    RE-PINNED 2026-07-17 (the fire-alarm ruling): the two historic `iotag_duplicate` FAILs were a
    CONFIG defect - the F1/2+F2/2 rows shared one tag rule over one shared device - not a fixture
    defect; the rule now disambiguates with {$script_type}, so phase 500's 510 leg WRITES PLCTags
    (asserted below). A halt anywhere in the chain is a regression."""
    doc_path = config.load_params()["iolist_path"]
    doc_mtime = os.path.getmtime(doc_path)
    for number in SYSTEM.phases.run_order():
        phase = SYSTEM.phases.by_number(number)
        host = _Host()
        SYSTEM.handlers[phase.handler](host.ctx())
        ok("RSLT" in host.levels(), f"phase {number} ({phase.handler}) emitted a RSLT line "
                                    f"(got {host.levels()})")
        eq(host.halted, False, f"phase {number} must not halt on the clean fixture")
        if number == 500:
            ok(any("510:" in msg for lvl, msg in host.lines if lvl == "RSLT"),
               "the 510 leg reports its written tag surface (PLCTags is a real output again)")
    eq(os.path.getmtime(doc_path), doc_mtime,
       "the source I/O List was NOT modified by the run_plan chain")


def test_sub_phase_dispatch():
    """A dropdown action: the parent handler with only=<sub> - the 310 stage-I/O-List leg, plus a
    validation sub (110), through the same dispatch the App's _sub_worker performs."""
    host = _Host()
    phase = SYSTEM.phases.phase_of_sub(310)
    SYSTEM.handlers[phase.handler](host.ctx(), only=310)
    ok(any("310" in msg for _lvl, msg in host.lines), "the 310 leg announces itself")
    ok("RSLT" in host.levels(), "the 310 leg reports a RSLT")
    host2 = _Host()
    phase = SYSTEM.phases.phase_of_sub(110)
    SYSTEM.handlers[phase.handler](host2.ctx(), only=110)
    ok("RSLT" in host2.levels(), "the 110 validator reports a RSLT")


if __name__ == "__main__":
    import sys
    sys.exit(run("siemens_main_handlers", [
        ("run_plan_executes_end_to_end", _sandboxed(test_run_plan_executes_end_to_end)),
        ("sub_phase_dispatch", _sandboxed(test_sub_phase_dispatch)),
    ]))
