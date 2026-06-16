#!/usr/bin/env python3
"""Synthetic test for the C&E/AREA -> I/O List cross-validation: covers match,
missing device, address mismatch, and AREA sheets. Run: python test_validation.py
"""
import os
import tempfile
from openpyxl import Workbook

from safetydb import validation

failures = 0


def check(name, ok, detail=""):
    global failures
    print(("PASS  " if ok else "FAIL  ") + name + (f"  [{detail}]" if detail else ""))
    if not ok:
        failures += 1


def _text(ws, cell, value):
    """Write a literal string; '=' values would otherwise become formulas
    (the real document stores these tags as text)."""
    ws[cell] = value
    if isinstance(value, str) and value.startswith("="):
        ws[cell].data_type = "s"


def make_ce(path):
    wb = Workbook()
    m = wb.active
    m.title = "CAUSE&EFFECT MATRIX"
    # header row 2: F=BIT, J=FUNCTIONAL UNIT, K=LOCATION, L=DEVICE
    m["F2"], m["J2"], m["K2"], m["L2"] = "BIT (ADDRESS)", "FUNCTIONAL UNIT", "LOCATION", "DEVICE"
    # data from row 5
    rows = [
        ("I20.0", "=S1", "+MS1.CC1", "-S67001"),   # match
        ("I20.9", "=S1", "+MS1.CC1", "-S67001"),   # device ok, address mismatch
        ("I120.0", "=S1", "+SG1", "-B1"),          # device missing
    ]
    for i, (addr, fu, loc, dev) in enumerate(rows, start=5):
        m[f"F{i}"] = addr
        _text(m, f"J{i}", fu)
        _text(m, f"K{i}", loc)
        _text(m, f"L{i}", dev)

    a = wb.create_sheet("AREA 1")
    a["A3"], a["C3"] = "SIGLA CONTATTORE", "DIGITAL OUTPUT"  # header row 3
    _text(a, "A4", "=S1+PC1.CC1-K65060")                     # data row 4 - missing
    a["C4"] = "Q130.0"
    wb.save(path)


def main():
    tmp = tempfile.mkdtemp(prefix="valtest_")
    ce_path = os.path.join(tmp, "ce.xlsx")
    make_ce(ce_path)

    io_rows = [
        {"functional_unit": "=S1", "location": "+MS1.CC1", "device": "-S67001", "bit": "I20.0",
         "desc_l1": "MAIN ESTOP", "drawing": "DWG-100", "script_type": "E1/2", "index": "0001"},
        {"functional_unit": "=S1", "location": "+MS1.CC1", "device": "-S67002", "bit": "I20.2"},
    ]
    params = {"io_list": {"path": "io.xlsx"},
              "ce": {"path": ce_path, "matrix_sheet": "CAUSE&EFFECT MATRIX",
                     "matrix_header_row": 2, "matrix_data_row": 5,
                     "area_header_row": 3, "area_data_row": 4}}

    log = validation.validate(params, io_rows)
    for e in log:
        print("   " + e.format())

    def find(loc):
        return next((e for e in log if e.location == loc), None)

    check("F5 device+address match -> PASS", find("CAUSE&EFFECT MATRIX!F5").level == "PASS")
    e = find("CAUSE&EFFECT MATRIX!F6")
    check("F6 address mismatch -> FAIL", e.level == "FAIL" and "mismatch" in e.message)
    e = find("CAUSE&EFFECT MATRIX!F7")
    check("F7 missing device -> FAIL", e.level == "FAIL" and "not found" in e.message)
    e = find("AREA 1!C4")
    check("AREA 1 C4 checked with cell address -> FAIL", e is not None and e.level == "FAIL")
    check("log includes passes and fails", any(x.level == "PASS" for x in log) and any(x.level == "FAIL" for x in log))

    # --- params.json logged at the start --------------------------------
    pj = next((e for e in log if e.location == "params.json"), None)
    check("params.json logged on validation start (before phase 1)",
          pj is not None and pj.level == "INFO" and '"io_list"' in pj.message
          and log.index(pj) < next(i for i, e in enumerate(log) if e.level == "PHASE"))

    # --- 3 clearly separated phases + the per-entry info block ----------
    phases = [e for e in log if e.level == "PHASE"]
    check("log is split into 3 phases", len(phases) == 3)
    check("phase 1 = C&E in IOList, 2 = IOList in C&E, 3 = Diagnosis Coherence Check",
          len(phases) == 3 and "C&E in IOList" in phases[0].message
          and "IOList in C&E" in phases[1].message
          and "Diagnosis Coherence Check" in phases[2].message)
    e5 = find("CAUSE&EFFECT MATRIX!F5")
    check("entry info block = bit | desc_l1 desc_l1b | FLD | drawing | script_type-index",
          all(s in e5.info() for s in ("I20.0", "MAIN ESTOP", "=S1+MS1.CC1-S67001", "DWG-100", "E1/2-0001"))
          and e5.info().count("|") == 4, e5.info())
    check("format() of a FAIL carries the info block", "|" in find("CAUSE&EFFECT MATRIX!F6").format())

    # --- diagnosis bit map checks ---------------------------------------
    def drow(cab, bit, thw, dev, srow, in_diag=True):
        return {"diag_cabinet": cab, "diag_bit": bit, "type_hw": thw,
                "functional_unit": "=S1", "location": "+PC1.CC1", "device": dev,
                "_source_sheet": "NET SAFETY 50", "_source_row": srow,
                "_type": {"in_diagnosis": in_diag}}

    diag_rows = [
        drow("014", "00", "A", "-F1", 11),                 # unique alarm -> PASS
        drow("014", "01", "A", "-F2", 12),                 # collides with -F3 below
        drow("014", "01", "A", "-F3", 13),                 # duplicate alarm slot 014.01
        drow("014", "01", "AW", "-W1", 14),                # same cab/bit but WARNING family -> ok
        drow("", "05", "A", "-F5", 15),                    # missing Diag Cabinet
        drow("014", "", "A", "-F6", 16),                   # missing Diag Bit
        drow("", "", "A", "-X9", 17, in_diag=False),       # not in-diagnosis -> ignored
    ]
    dlog = []
    validation.check_diagnosis_bits({"io_list": {"path": "io.xlsx"}}, diag_rows, dlog)
    for e in dlog:
        print("   " + e.format())
    fails = [e for e in dlog if e.level == "FAIL"]
    dups = [e for e in fails if "duplicate" in e.message]
    miss = [e for e in fails if "missing" in e.message]
    check("duplicate alarm slot 014.01 flagged on BOTH rows", len(dups) == 2
          and all("ALARM" in e.address for e in dups))
    check("warning at same cab/bit is a separate slot -> PASS",
          any(e.level == "PASS" and "WARNING" in e.address for e in dlog))
    check("missing Diag Cabinet -> FAIL", any("Diag Cabinet" in e.message for e in miss))
    check("missing Diag Bit -> FAIL", any("Diag Bit" in e.message for e in miss))
    check("non in-diagnosis row ignored", all("-X9" not in (e.key or "") for e in dlog))
    check("diagnosis entries link to the I/O List path",
          all(e.path == "io.xlsx" for e in dlog if e.level in ("PASS", "FAIL")))
    check("diagnosis entry locations point at AE/AF cells",
          all(("!AE" in e.location or "!AF" in e.location) for e in fails + [e for e in dlog if e.level == "PASS"]))

    # --- reverse C&E: I/O List signals that must appear in the C&E ------
    # ce (key @ addr) in make_ce: =S1+MS1.CC1-S67001 @ I20.0 & I20.9, =S1+SG1-B1 @ I120.0,
    #                             =S1+PC1.CC1-K65060 @ Q130.0
    def trow(fu, loc, dev, bit, mand=None, desc="", desc_b="", srow=30):
        r = {"functional_unit": fu, "location": loc, "device": dev, "bit": bit,
             "desc_l1": desc, "desc_l1b": desc_b, "_source_sheet": "NET SAFETY 50", "_source_row": srow}
        r["_type"] = {"ce_mandatory": mand} if mand is not None else None
        return r

    ce_rows = [
        trow("=S1", "+MS1.CC1", "-S67001", "I20.0", mand="yes", srow=30),   # full match -> PASS
        trow("=S1", "+XX1", "-S99001", "I21.0", mand="yes", srow=31),       # absent, yes -> FAIL
        trow("=S1", "+XX2", "-S99002", "I22.0", mand="warn", srow=32),      # absent, warn -> WARN
        trow("=S1", "+XX3", "-S99003", "I23.0", mand="no", srow=33),        # absent, no -> skipped
        trow("=S1", "+EM1", "-S88001", "I24.0", desc="EMERGENCY STOP PB", srow=34),  # untyped + safety -> FAIL
        trow("=S1", "+CV1", "-M70001", "Q24.0", desc="CONVEYOR MOTOR RUN", srow=35),  # untyped, no kw -> WARN
        trow("=S1", "+SG1", "-B1", "I120.0", desc="WHATEVER", srow=36),     # full match -> no entry
        trow("=S1", "+ZZ1", "-X1", "", desc="EMERGENCY", srow=37),          # untyped, no address -> skipped
        trow("=S1", "+SF1", "-K90001", "I28.0", desc="SAFTY RELAY MODULE", srow=38),  # untyped, fuzzy 'safty' -> FAIL
        trow("=S1", "+MS1.CC1", "", "I9.0", desc="", srow=39),              # untyped, no device + no desc -> skipped
        trow("=S1", "+MS1.CC1", "-S67001", "I20.5", mand="yes", srow=40),   # FLD found, addr differs -> FAIL
        trow("=S1", "+SG9", "-B9", "I120.0", desc="PLAIN", srow=41),        # addr found, FLD differs -> WARN
        trow("=S1", "+MS1.CC1", "", "I30.0", desc="", desc_b="SOME SIGNAL", srow=42),  # device-less but desc_l1b -> WARN
    ]
    clog = []
    validation.check_ce_mandatory(params, ce_rows, clog)
    for e in clog:
        print("   " + e.format())

    def crow(srow):
        return next((e for e in clog if e.location.endswith(f"!O{srow}")), None)

    check("ce_mandatory=yes full match -> PASS", crow(30) and crow(30).level == "PASS")
    check("ce_mandatory=yes absent -> FAIL", crow(31) and crow(31).level == "FAIL")
    check("ce_mandatory=warn absent -> WARN", crow(32) and crow(32).level == "WARN")
    check("ce_mandatory=no absent -> not checked", crow(33) is None)
    check("untyped + safety word (EMERGENCY) absent -> FAIL", crow(34) and crow(34).level == "FAIL")
    check("untyped, no safety word absent -> WARN", crow(35) and crow(35).level == "WARN")
    check("untyped full match in C&E -> PASS (always logged)", crow(36) and crow(36).level == "PASS")
    check("untyped without an address -> not checked", crow(37) is None)
    check("untyped + fuzzy 'safty' (<=2 of safety) -> FAIL", crow(38) and crow(38).level == "FAIL")
    check("untyped without a device and no desc (spare) -> not checked", crow(39) is None)
    check("FLD found but address differs -> FAIL (same severity), prints both sides",
          crow(40) and crow(40).level == "FAIL" and "I20.5" in crow(40).message
          and "I20.0" in crow(40).message and "different address" in crow(40).message)
    check("address found but FLD differs -> WARN, prints both sides",
          crow(41) and crow(41).level == "WARN" and "=S1+SG9-B9" in crow(41).message
          and "=S1+SG1-B1" in crow(41).message and "different device" in crow(41).message)
    check("device-less row with desc_l1b text IS checked -> WARN", crow(42) and crow(42).level == "WARN")
    check("reverse-C&E entries link to the I/O List path",
          all(e.path == params["io_list"]["path"] for e in clog if e.level in ("PASS", "FAIL", "WARN")))

    # --- fuzzy / word-list parameters -----------------------------------
    W = ["emergency", "safety", "relay", "contactor", "enable"]
    check("fuzzy=0 keeps exact substring ('SAFETY DOOR')", validation._matches_words("SAFETY DOOR", W, 0))
    check("fuzzy=0 drops near-miss ('SAFTY DOOR')", not validation._matches_words("SAFTY DOOR", W, 0))
    check("fuzzy=2 catches near-miss ('SAFTY DOOR')", validation._matches_words("SAFTY DOOR", W, 2))
    check("multi-word phrase matches as substring ('circuit breaker')",
          validation._matches_words("400V CIRCUIT BREAKER TRIP", ["circuit breaker"], 0))
    check("custom word list is honored", validation._matches_words("VALVE OPEN", ["valve"], 0)
          and not validation._matches_words("VALVE OPEN", W, 2))

    # --- ce_excluded_words + ce_full_check ------------------------------
    excl = ["circuit breaker", "power supply", "profinet switch", "coupler", "door"]
    ex_rows = [
        trow("=S1", "+CB1", "-F50001", "I40.0", desc="CIRCUIT BREAKER TRIP 400V", srow=50),  # excluded -> skip
        trow("=S1", "+DR1", "-B5", "I41.0", desc="SAFETY DOOR OPEN", srow=51),    # excluded 'door' but 'safety' wins -> FAIL
        trow("=S1", "+DR2", "-B6", "I42.0", mand="yes", desc="MAIN DOOR CLOSED", srow=52),  # typed -> rules prevail -> FAIL
        trow("=S1", "+PS1", "-T1", "I43.0", desc="POWER SUPPLY UNIT FAULT", srow=53),  # excluded -> skip
        trow("=S1", "+GN1", "-M1", "I44.0", desc="TANK LEVEL HIGH", srow=54),    # not excluded, no safety -> WARN
    ]
    xlog = []
    validation.check_ce_mandatory(dict(params, ce_excluded_words=excl), ex_rows, xlog)
    for e in xlog:
        print("   " + e.format())

    def xrow(srow):
        return next((e for e in xlog if e.location.endswith(f"!O{srow}")), None)

    check("untyped excluded word (circuit breaker) -> SKIP", xrow(50) and xrow(50).level == "SKIP")
    check("excluded 'door' but mandatory 'safety' wins -> FAIL", xrow(51) and xrow(51).level == "FAIL")
    check("typed row never excluded (signal-type rules prevail) -> FAIL", xrow(52) and xrow(52).level == "FAIL")
    check("untyped excluded word (power supply) -> SKIP", xrow(53) and xrow(53).level == "SKIP")
    check("non-excluded untyped, no safety -> WARN", xrow(54) and xrow(54).level == "WARN")
    check("SKIP entry names the matched excluded word",
          xrow(50) and "circuit breaker" in xrow(50).message)
    check("an INFO records how many rows were excluded",
          any(e.level == "INFO" and "skipped" in e.message for e in xlog))

    flog = []
    validation.check_ce_mandatory(
        dict(params, ce_excluded_words=excl, ce_full_check=True),
        [trow("=S1", "+CB9", "-F9", "I49.0", desc="CIRCUIT BREAKER TRIP", srow=60)], flog)
    frow = next((e for e in flog if e.location.endswith("!O60")), None)
    check("ce_full_check ignores exclusions (circuit breaker now checked) -> WARN",
          frow and frow.level == "WARN")

    # --- ce_always_excluded_words (substring only, no fuzzy, wins all) ---
    aw_rows = [
        trow("=S1", "+A1", "-X1", "I60.0", desc="SOMETHING CH2", srow=70),                # untyped + ch2 -> SKIP
        trow("=S1", "+A2", "-X2", "I61.0", mand="yes", desc="SAFETY RELAY CH2", srow=71), # typed yes + ch2 -> SKIP (wins all)
        trow("=S1", "+A3", "-X3", "I62.0", desc="CHANNEL TWO", srow=72),                  # no 'ch2' substring -> WARN
    ]
    awlog = []
    validation.check_ce_mandatory(
        dict(params, ce_always_excluded_words=["ch2"], ce_full_check=True), aw_rows, awlog)

    def awrow(srow):
        return next((e for e in awlog if e.location.endswith(f"!O{srow}")), None)

    check("ce_always_excluded 'ch2' skips an untyped row -> SKIP", awrow(70) and awrow(70).level == "SKIP")
    check("ce_always_excluded wins over signal-type + mandatory (typed yes ch2) -> SKIP",
          awrow(71) and awrow(71).level == "SKIP")
    check("ce_always_excluded is substring-only/no-fuzzy ('channel two' != ch2) -> WARN",
          awrow(72) and awrow(72).level == "WARN")
    check("ce_full_check does NOT bypass ce_always_excluded_words", awrow(70) and awrow(70).level == "SKIP")

    # --- HTML export (validation_log.html), colour-coded, same layout --
    out = tempfile.mkdtemp(prefix="vallog_")
    validation.write_log(log, out)
    html = open(os.path.join(out, "validation_log.html"), encoding="utf-8").read()
    check("validation_log.html = dark page, phase <h2>, coloured entry <div>s, FAIL CSS",
          "<!DOCTYPE html" in html and '<h2 class="phase">' in html
          and 'class="entry FAIL"' in html and "#ff6b6b" in html)
    check("validation_log.html escapes & (CAUSE&EFFECT); no leftover <span> markup",
          "CAUSE&amp;EFFECT" in html and "<span" not in html)
    check("the superseded validation_log.md is removed",
          not os.path.exists(os.path.join(out, "validation_log.md")))
    txt = open(os.path.join(out, "validation_log.txt"), encoding="utf-8").read()
    check("validation_log.txt SUMMARY includes the skipped count", "skipped" in txt.splitlines()[-1])

    print("ALL CHECKS PASS" if failures == 0 else f"{failures} CHECK(S) FAILED")
    raise SystemExit(0 if failures == 0 else 1)


if __name__ == "__main__":
    main()
