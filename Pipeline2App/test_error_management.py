#!/usr/bin/env python3
"""Tests for the error registry + per-error treatment (pipeline2/core/error_management.py).

Phase tagging (EN "PHASE"/IT "FASE"), the normalised error "type" (skip_type), the per-instance
id, writing the registry CSV, and applying warn/skip/skip_type on a subsequent run. Plus a light
validate(out_dir=...) integration that the CSV gets written.

Run: python test_error_management.py
"""
import csv
import os
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from pipeline2.core import error_management as em
from pipeline2.core.validation import LogEntry

failures = 0


def check(name, ok, detail=""):
    global failures
    print(("PASS  " if ok else "FAIL  ") + name + (f"  [{detail}]" if detail else ""))
    if not ok:
        failures += 1


def sample_log():
    """A small log with FAILs across phases (EN + IT banners), like a real validation run."""
    return [
        LogEntry("PHASE", "", "", "", "PHASE 0A - I/O List standalone validation"),
        LogEntry("FAIL", "NET SAFETY 50!U281", "FU1L1D1", "",
                 "[ER] TS ref is missing [sheet 'NET SAFETY 50' - cell 'U281']"),
        LogEntry("FAIL", "NET SAFETY 50!U282", "FU2L1D1", "",
                 "[ER] TS ref is missing [sheet 'NET SAFETY 50' - cell 'U282']"),
        LogEntry("FAIL", "NET SAFETY 50!V270", "", "192.168.50.6",
                 "[ER] Duplicated IP found 192.168.50.6 [sheet 'NET SAFETY 50' - cell 'V270']"),
        LogEntry("INFO", "I/O List", "", "", "12 distinct device key(s) indexed"),
        LogEntry("PHASE", "", "", "", "PHASE 1 - C&E in IOList"),
        LogEntry("FAIL", "CAUSE&EFFECT MATRIX!F7", "K1", "I0.0", "reference not found in I/O List"),
    ]


def fails(log):
    return [e for e in log if e.level == "FAIL"]


def main():
    # --- phase tagging (EN + an IT banner) ----------------------------------
    log = sample_log()
    log[5].message = "FASE 1 - C&E in IOList"          # IT banner still parses the id "1"
    em.assign_phases(log)
    f = fails(log)
    check("0A fails tagged 0A", all(e.phase == "0A" for e in f[:3]), str([e.phase for e in f]))
    check("phase-1 fail tagged 1 (IT 'FASE' banner)", f[3].phase == "1")

    # --- error_type strips the variable parts (groups a check's instances) --
    t1 = em.error_type(f[0].message)   # U281
    t2 = em.error_type(f[1].message)   # U282
    check("same check -> same type (cells differ)", t1 == t2 and t1 == "TS ref is missing", t1)
    check("dup-IP type drops the IP + cell", em.error_type(f[2].message) == "Duplicated IP found",
          em.error_type(f[2].message))

    # --- error_id: deterministic + unique per instance ----------------------
    log2 = sample_log()
    log2[5].message = "FASE 1 - C&E in IOList"
    em.assign_phases(log2)
    f2 = fails(log2)
    check("id deterministic", em.error_id(f[0]) == em.error_id(f2[0]))
    check("id unique per instance", em.error_id(f[0]) != em.error_id(f[1]))

    # --- run(): writes the registry, no rules yet -> levels unchanged -------
    tmp = tempfile.mkdtemp(prefix="errmgmt_")
    log = sample_log()
    path = em.run(log, tmp)
    check("registry written", os.path.exists(path) and path.endswith(em.CSV_NAME))
    with open(path, encoding="utf-8-sig", newline="") as fp:
        rows = list(csv.DictReader(fp))
    check("registry header", set(em.HEADER) == set(rows[0].keys()) if rows else False)
    check("one row per distinct fail (4)", len(rows) == 4, str(len(rows)))
    check("ids present, treatment blank", all(r["id"] and r["treatment"] == "" for r in rows))
    check("run() left levels FAIL (no rules)", all(e.level == "FAIL" for e in fails(log)))

    # --- pre-seed treatments, run again -> warn / skip / skip_type applied --
    ids = {em.error_id(e): e for e in f2}        # f2 has phases assigned
    id_u281 = em.error_id(f2[0])
    id_dupip = em.error_id(f2[2])
    id_ce = em.error_id(f2[3])
    with open(path, "w", encoding="utf-8-sig", newline="") as fp:
        w = csv.DictWriter(fp, fieldnames=em.HEADER)
        w.writeheader()
        w.writerow({"id": id_u281, "phase": "0A", "type": "TS ref is missing",
                    "treatment": "skip_type", "location": "", "message": ""})
        w.writerow({"id": id_dupip, "phase": "0A", "type": "Duplicated IP found",
                    "treatment": "skip", "location": "", "message": ""})
        w.writerow({"id": id_ce, "phase": "1", "type": "reference not found in I/O List",
                    "treatment": "warn", "location": "", "message": ""})

    log3 = sample_log()
    em.run(log3, tmp)
    lv = {e.location: e.level for e in log3 if e.level in ("FAIL", "WARN", "SKIP")}
    check("skip_type skips ALL of that type (U281 + U282)",
          lv.get("NET SAFETY 50!U281") == "SKIP" and lv.get("NET SAFETY 50!U282") == "SKIP", str(lv))
    check("skip skips that one error", lv.get("NET SAFETY 50!V270") == "SKIP")
    check("warn downgrades that one error", lv.get("CAUSE&EFFECT MATRIX!F7") == "WARN")
    check("treated message carries an audit note",
          "[skipped by error_management]" in next(e.message for e in log3 if e.location == "NET SAFETY 50!U281"))

    # --- rewrite preserves treatments by id (merge) -------------------------
    with open(path, encoding="utf-8-sig", newline="") as fp:
        merged = {r["id"]: r["treatment"] for r in csv.DictReader(fp)}
    check("treatment preserved across runs", merged.get(id_u281) == "skip_type" and merged.get(id_ce) == "warn")

    # --- validate(out_dir=...) writes the registry to user_input/ (light integration) ------
    from pipeline2.core import validation, config
    tmp2 = tempfile.mkdtemp(prefix="errmgmt_val_")
    saved = config.USER_INPUT
    config.USER_INPUT = tmp2                       # isolate: don't touch the real user_input/
    try:
        validation.validate({"io_list": {}, "ce": {}}, [], phases={"0B"}, out_dir=tmp2)
    finally:
        config.USER_INPUT = saved
    check("validate(out_dir) writes the registry to user_input/",
          os.path.exists(os.path.join(tmp2, em.CSV_NAME)))

    print("ALL CHECKS PASS" if failures == 0 else f"{failures} CHECK(S) FAILED")
    raise SystemExit(0 if failures == 0 else 1)


if __name__ == "__main__":
    main()
