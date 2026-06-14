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
    diag = script in ("A", "W", "PA", "PW", "DD")
    cat = "Interface" if script == "IOC" else ("Diag" if diag else "Safety")
    return {
        "script_type": script, "functional_unit": fu, "location": loc, "device": dev,
        "bit": bit, "desc_l1": d1, "desc_l1b": d2, "index": index,
        "drawing": drawing, "sheet": sheet, "type_hw": "A" if diag else "P",
        "diag_cabinet": "001", "diag_bit": "00", "id_node": "5",
        "_type": {"description": f"Desc-{script}", "category": cat, "db_kind": db_kind,
                  "in_diagnosis": diag},
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
        # E1/2 and KQ share one safe DB by db_name; A has none
        signal_types = {
            "E1/2": {"db_kind": "safe_db", "db_name": "01_Pushbutton"},
            "A": {"db_kind": "", "db_name": ""},
            "KQ": {"db_kind": "safe_db", "db_name": "01_Pushbutton"},
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

        dbs = outputs.build_dbs(rows, signal_types)
        check("DB grouped by db_name (E1/2 + KQ share one)", set(dbs) == {"01_Pushbutton"}, str(list(dbs)))
        check("shared DB is fail-safe", dbs["01_Pushbutton"]["kind"] == "safe_db")
        members = dbs["01_Pushbutton"]["members"]
        check("shared DB combines both types' tags",
              tables["E1/2"][0]["name"] in members and tables["KQ"][0]["name"] in members)
        outputs.write_dbs(dbs, tmp)
        with open(os.path.join(tmp, "DBs", "01_Pushbutton.db"), encoding="utf-8") as f:
            body = f.read()
        check("DB source has DATA_BLOCK + member", "DATA_BLOCK" in body and tables["KQ"][0]["name"] in body)

        # diagnosis List_IO: only in_diagnosis types (A), not safety (E1/2,KQ)
        diag = outputs.build_diagnosis_list_io(rows)
        check("diagnosis includes only in-diagnosis types", {d["DevType"] for d in diag} == {"A"})
        check("diagnosis row has the 17 List_IO columns",
              [c[0] for c in outputs.DIAG_COLUMNS][:3] == ["Diag Cabinet", "Diag Bit", "DevType"]
              and diag[0]["Device"] == "-F09001")
        # both A rows are in-diagnosis (incl. the address-less base-addr row)
        n = outputs.write_diagnosis_list_io(diag, tmp)
        check("diagnosis CSV written (address-less rows included)",
              n == 2 and os.path.exists(os.path.join(tmp, "Diagnosis", "List_IO.csv")))

        print("ALL CHECKS PASS" if failures == 0 else f"{failures} CHECK(S) FAILED")
        raise SystemExit(0 if failures == 0 else 1)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
