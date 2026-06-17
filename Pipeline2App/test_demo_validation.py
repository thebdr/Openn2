#!/usr/bin/env python3
"""Regression test for the demo input workbooks (make_demo_inputs.py): builds them into a temp
dir and asserts the validation log contains one example of EVERY case across the three phases.
Run: python test_demo_validation.py"""
import os
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from pipeline2.core import config, staging, validation
import make_demo_inputs

failures = 0


def check(name, ok, detail=""):
    global failures
    print(("PASS  " if ok else "FAIL  ") + name + (f"  [{detail}]" if detail else ""))
    if not ok:
        failures += 1


def main():
    tmp = tempfile.mkdtemp(prefix="demoval_")
    io_path = os.path.join(tmp, "io.xlsx")
    ce_path = os.path.join(tmp, "ce.xlsx")
    make_demo_inputs.build(io_path, ce_path)
    params = make_demo_inputs.demo_params(io_path, ce_path, out_dir=tmp)

    rows, warns = staging.load_io_list(params, config.load_signal_types())
    check("demo I/O List loads cleanly (no header mismatch)",
          not [w for w in warns if "header" in w and "!=" in w], "; ".join(warns[1:]) or "clean")

    # cross-check + diagnosis phases (Phase 0A standalone is covered in test_iolist_checks.py)
    log = validation.validate(params, rows, phases={"1", "2", "3"})
    validation.write_log(log, tmp)            # also exercises the .txt/.html writers

    def at(loc):
        return next((e for e in log if e.location == loc), None)

    def lvl(loc):
        e = at(loc)
        return e.level if e else None

    # ---- Phase 1: C&E in IOList (forward) ------------------------------
    check("P1 forward PASS (C&E ref matches I/O)", lvl("CAUSE&EFFECT MATRIX!F5") == "PASS")
    e = at("CAUSE&EFFECT MATRIX!F6")
    check("P1 forward FAIL address mismatch",
          e and e.level == "FAIL" and "different address" in e.message
          and e.cmp and e.cmp.fld_eq and not e.cmp.addr_eq)
    e = at("CAUSE&EFFECT MATRIX!F7")
    check("P1 forward FAIL device not found",
          e and e.level == "FAIL" and "not declared" in e.message)
    e = at("CAUSE&EFFECT MATRIX!F9")
    check("P1 forward FAIL empty device key",
          e and e.level == "FAIL" and "no device designation" in e.message)
    check("P1 AREA forward PASS", lvl("AREA 1!C4") == "PASS")
    check("P1 AREA forward FAIL (not found)", lvl("AREA 1!C5") == "FAIL")

    # ---- Phase 2: IOList in C&E (reverse) ------------------------------
    check("P2 reverse PASS (typed mandatory present)", lvl("NET SAFETY 50!O2") == "PASS")
    e = at("NET SAFETY 50!O3")
    check("P2 reverse FAIL ce_mandatory=yes absent", e and e.level == "FAIL" and "absent" in e.message)
    e = at("NET SAFETY 50!O4")
    check("P2 reverse WARN ce_mandatory=warn absent", e and e.level == "WARN")
    e = at("NET SAFETY 50!O5")
    check("P2 reverse FAIL fld-only partial (address differs)",
          e and e.level == "FAIL" and "different address" in e.message
          and e.cmp and e.cmp.fld_eq and not e.cmp.addr_eq
          and "I9.9" in (e.cmp.caller_addr + e.cmp.other_addr))
    e = at("NET SAFETY 50!O6")
    check("P2 reverse FAIL addr-only partial (device differs)",
          e and e.level == "FAIL" and "different device" in e.message
          and e.cmp and not e.cmp.fld_eq and e.cmp.addr_eq
          and "S19999" in (e.cmp.caller_fld + e.cmp.other_fld))
    e = at("NET SAFETY 50!O7")
    check("P2 reverse FAIL untyped + safety word", e and e.level == "FAIL" and "Safety-related" in e.message)
    e = at("NET SAFETY 50!O8")
    check("P2 reverse WARN untyped, no safety word", e and e.level == "WARN")
    e = at("NET SAFETY 50!O9")
    check("P2 reverse SKIP ce_excluded_words", e and e.level == "SKIP" and "power supply" in e.message)
    e = at("NET SAFETY 50!O10")
    check("P2 reverse SKIP ce_always_excluded_words (ch2 wins over mandatory)",
          e and e.level == "SKIP" and "ch2" in e.message)
    check("P2 reverse PASS (untyped present in C&E)", lvl("NET SAFETY 50!O11") == "PASS")
    check("P2 reverse PASS (KQ present via AREA sheet)", lvl("NET SAFETY 50!O12") == "PASS")

    # ---- Phase 3: Diagnosis Coherence Check ----------------------------
    e = at("NET SAFETY 50!AE14")
    check("P3 diagnosis FAIL missing Diag Cabinet", e and e.level == "FAIL" and "Diag Cabinet" in e.message)
    e = at("NET SAFETY 50!AF15")
    check("P3 diagnosis FAIL missing Diag Bit", e and e.level == "FAIL" and "Diag Bit" in e.message)
    dups = [e for e in log if e.level == "FAIL" and "duplicate diagnosis slot" in e.message]
    check("P3 diagnosis FAIL duplicate slot (both rows)", len(dups) == 2)
    check("P3 diagnosis PASS (unique alarm + warning slots)",
          any(e.level == "PASS" and "ALARM" in e.address for e in log)
          and any(e.level == "PASS" and "WARNING" in e.address for e in log))

    # ---- structure: every severity present + 3 phases + params logged --
    levels = {e.level for e in log}
    check("all severities present (PASS/FAIL/WARN/SKIP)", {"PASS", "FAIL", "WARN", "SKIP"} <= levels)
    check("3 phase banners + params.yaml header",
          sum(1 for e in log if e.level == "PHASE") == 3
          and any(e.location == "params.yaml" for e in log))

    print("ALL CHECKS PASS" if failures == 0 else f"{failures} CHECK(S) FAILED")
    raise SystemExit(0 if failures == 0 else 1)


if __name__ == "__main__":
    main()
