#!/usr/bin/env python3
"""Synthetic test for I/O tag + DB generation. Run: python test_outputs.py"""
import os
import shutil
import tempfile
from openpyxl import load_workbook
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
        # E1/2 + KQ share 01_Pushbutton (safe); KQ also feeds a second DB via '|'
        # and carries an add_to_name suffix; A has no DB.
        signal_types = {
            "E1/2": {"db_kind": "safe_db", "db_names": ["01_Pushbutton"], "add_to_name": ""},
            "A":    {"db_kind": "",        "db_names": [],                 "add_to_name": ""},
            "KQ":   {"db_kind": "safe_db", "db_names": ["01_Pushbutton", "01_Pushbutton_RAW"], "add_to_name": "Error"},
        }

        tables = outputs.build_io_tags(rows)
        check("one table per type (tagtable_name absent -> type id), interface + non-IO excluded",
              set(tables) == {"E1/2", "A", "KQ"}, str(sorted(tables)))
        check("counts (A has 1 taggable, not the base-addr row)",
              len(tables["A"]) == 1 and len(tables["E1/2"]) == 1 and len(tables["KQ"]) == 1)

        e = tables["E1/2"][0]
        check("safety tag name = type description + FLD",
              e["name"] == "Desc-E1/2 =S1+MS1.CC1-S67001", e["name"])
        check("comment format",
              e["comment"] == "[E1/2 0001] EMERGENCY CH1 [DWG1 670]", e["comment"])
        check("logical address is %-prefixed", e["address"] == "%I20.0", e["address"])

        a = tables["A"][0]
        check("alarm tag name = descr1 p1+p2 (space) + FLD",
              a["name"] == "CIRCUIT BREAKER 400V =S1+MS1.CC1-F09001", a["name"])

        outputs.write_io_tags(tables, tmp)
        xlsx = os.path.join(tmp, "IoTags", "PLCTags.xlsx")
        check("single PLC Tags xlsx written", os.path.exists(xlsx))
        wb = load_workbook(xlsx)
        check("two sheets: PLC Tags + TagTable Properties",
              wb.sheetnames == ["PLC Tags", "TagTable Properties"], str(wb.sheetnames))
        ws = wb["PLC Tags"]
        check("PLC Tags header matches TIA export",
              [c.value for c in ws[1]] == outputs.TAG_COLUMNS)
        rowvals = [[c.value for c in r] for r in ws.iter_rows(min_row=2)]
        e_row = next((rv for rv in rowvals if rv[0] == "Desc-E1/2 =S1+MS1.CC1-S67001"), None)
        check("tag row: Path + %-address + text 'True' flags",
              e_row is not None and e_row[1] == "E1/2" and e_row[3] == "%I20.0" and e_row[5] == "True",
              str(e_row))
        paths = {r[0].value for r in wb["TagTable Properties"].iter_rows(min_row=2)}
        check("TagTable Properties lists the distinct tables", paths == {"E1/2", "A", "KQ"}, str(paths))

        dbs = outputs.build_dbs(rows, signal_types)
        check("DBs by db_names incl. the '|' multi (-> two)",
              set(dbs) == {"01_Pushbutton", "01_Pushbutton_RAW"}, str(sorted(dbs)))
        check("shared DB is fail-safe", dbs["01_Pushbutton"]["kind"] == "safe_db")
        mnames = lambda d: [m["name"] for m in dbs[d]["members"]]
        check("every DB opens with ALWAYS_FALSE + ALWAYS_TRUE",
              mnames("01_Pushbutton")[:2] == ["ALWAYS_FALSE", "ALWAYS_TRUE"]
              and mnames("01_Pushbutton_RAW")[:2] == ["ALWAYS_FALSE", "ALWAYS_TRUE"])
        check("01_Pushbutton combines E1/2 + KQ members",
              "Desc-E1/2 =S1+MS1.CC1-S67001" in mnames("01_Pushbutton")
              and "Desc-KQ =S1+MS1.CC1-K1 Error" in mnames("01_Pushbutton"))
        check("add_to_name suffix on KQ member, in both its DBs",
              "Desc-KQ =S1+MS1.CC1-K1 Error" in mnames("01_Pushbutton_RAW"))
        kq = next(m for m in dbs["01_Pushbutton"]["members"] if m["name"].startswith("Desc-KQ"))
        check("DB member keeps the tag comment",
              kq["comment"].startswith("[KQ 0003]") and "[DWG3 120]" in kq["comment"], kq["comment"])
        outputs.write_dbs(dbs, tmp)
        with open(os.path.join(tmp, "DBs", "01_Pushbutton.db"), encoding="utf-8") as f:
            body = f.read()
        check("DB source: DATA_BLOCK + constant + //-commented member",
              'DATA_BLOCK "01_Pushbutton"' in body
              and '"ALWAYS_FALSE" : Bool;' in body
              and '"Desc-KQ =S1+MS1.CC1-K1 Error" : Bool; //[KQ 0003]' in body)

        # diagnosis List_IO: only in_diagnosis types (A), not safety (E1/2,KQ)
        diag = outputs.build_diagnosis_list_io(rows)
        check("diagnosis includes only in-diagnosis types", {d["DevType"] for d in diag} == {"A"})
        check("diagnosis row uses the config columns + PLC_Binding",
              diag[0]["Device"] == "-F09001" and "PLC_Binding" in diag[0])
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
