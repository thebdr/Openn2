#!/usr/bin/env python3
"""Synthetic test for I/O tag + DB generation. Run: python test_outputs.py"""
import os
import shutil
import tempfile
from safetydb import outputs

failures = 0


def check(name, ok, detail=""):
    global failures
    print(("PASS  " if ok else "FAIL  ") + name + (f"  [{detail}]" if detail else ""))
    if not ok:
        failures += 1


def row(script, fu, loc, dev, bit, d1="", d2="", index="", drawing="", sheet="", db_kind=""):
    cat = "Interface" if script == "IOC" else ("Diag" if script in ("A", "W", "PA", "PW") else "Safety")
    return {
        "script_type": script, "functional_unit": fu, "location": loc, "device": dev,
        "bit": bit, "desc_l1": d1, "desc_l1b": d2, "index": index,
        "drawing": drawing, "sheet": sheet,
        "_type": {"description": f"Desc-{script}", "category": cat, "db_kind": db_kind},
    }


def main():
    tmp = tempfile.mkdtemp(prefix="outtest_")
    try:
        rows = [
            row("E1/2", "=S1", "+MS1.CC1", "-S67001", "I20.0", "EMERGENCY", "CH1", "0001", "DWG1", "670"),
            row("A", "=S1", "+MS1.CC1", "-F09001", "I1.0", "CIRCUIT BREAKER", "400V", "0007", "DWG2", "653A"),
            row("KQ", "=S1", "+MS1.CC1", "-K1", "Q5.0", "", "", "0003", "DWG3", "120", db_kind="safe_db"),
            row("IOC", "=S1", "+MC1.CC1", "-K66201", "10000", index="SORTER-01"),   # excluded (interface)
            row("A", "=S1", "+MS1.CC1", "-X1", "10000", "BASE", "ADDR"),            # excluded (no I/Q addr)
        ]
        # mark KQ type as needing a safe DB
        signal_types = {
            "E1/2": {"db_kind": ""}, "A": {"db_kind": ""},
            "KQ": {"db_kind": "safe_db"},
        }

        tables = outputs.build_io_tags(rows)
        check("one table per type, interface + non-IO excluded",
              set(tables) == {"E1/2", "A", "KQ"}, str(sorted(tables)))
        check("counts (A has 1 taggable, not the base-addr row)",
              len(tables["A"]) == 1 and len(tables["E1/2"]) == 1 and len(tables["KQ"]) == 1)

        e = tables["E1/2"][0]
        check("safety tag name = type description + FLD",
              e["name"] == "Desc-E1/2 =S1+MS1.CC1-S67001", e["name"])
        check("comment format",
              e["comment"] == "[E1/2 0001] EMERGENCY CH1 [DWG1 670]", e["comment"])

        a = tables["A"][0]
        check("alarm tag name = descr1 p1+p2 (space) + FLD",
              a["name"] == "CIRCUIT BREAKER 400V =S1+MS1.CC1-F09001", a["name"])

        outputs.write_io_tags(tables, tmp)
        check("one CSV file per type", os.path.exists(os.path.join(tmp, "IoTags", "E1_2.csv")))
        with open(os.path.join(tmp, "IoTags", "A.csv"), encoding="utf-8-sig") as f:
            head = f.readline().strip()
        check("tag CSV header", head == "Name;Data Type;Logical Address;Comment", head)

        dbs = outputs.build_dbs(tables, signal_types)
        check("safe DB built for KQ only", set(dbs) == {"FDB_KQ"}, str(list(dbs)))
        check("DB member keeps tag name", dbs["FDB_KQ"]["members"] == [tables["KQ"][0]["name"]])
        outputs.write_dbs(dbs, tmp)
        with open(os.path.join(tmp, "DBs", "FDB_KQ.db"), encoding="utf-8") as f:
            body = f.read()
        check("DB source has DATA_BLOCK + member", "DATA_BLOCK" in body and tables["KQ"][0]["name"] in body)

        print("ALL CHECKS PASS" if failures == 0 else f"{failures} CHECK(S) FAILED")
        raise SystemExit(0 if failures == 0 else 1)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
