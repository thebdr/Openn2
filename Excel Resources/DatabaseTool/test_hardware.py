#!/usr/bin/env python3
"""Synthetic test for hardware Stations/Modules extraction. Run: python test_hardware.py"""
import os
import shutil
import tempfile
from safetydb import hardware

failures = 0


def check(name, ok, detail=""):
    global failures
    print(("PASS  " if ok else "FAIL  ") + name + (f"  [{detail}]" if detail else ""))
    if not ok:
        failures += 1


def row(script="", type_hw="", pn="", slot="", bit="", fu="=S1", loc="+M1", dev="-D1",
        ip="", pname="", idn=""):
    return {"script_type": script, "type_hw": type_hw, "part_no": pn, "slot": slot,
            "bit": bit, "functional_unit": fu, "location": loc, "device": dev,
            "profinet_ip": ip, "profinet_name": pname, "id_node": idn, "_source_row": 0}


def main():
    tmp = tempfile.mkdtemp(prefix="hwtest_")
    try:
        dtd = {
            "6ES7155-6AU01-0BN0": {"params": ""},
            "6ES7131-6BH01-0BA0": {"params": ""},
            "6ES7136-6BA01-0CA0": {"params": "Ch(0-7).Failsafe_DiscrepancyTime=100"},
        }
        rows = [
            row(script="PLC", pn="6ES7517-3FP00-0AB0", ip="192.168.50.1", pname="n0001-plc", idn="1"),
            row(script="PlcCardCm", pn="6GK7 542-1AX00-0XE0", ip="192.168.51.1", pname="n0001-cm", idn="1"),
            # IoDevice head (Type R first letter P)
            row(type_hw="PA", pn="6ES7155-6AU01-0BN0", ip="192.168.50.5", pname="n0005-im", idn="5"),
            # card 1: two DI signals -> I start byte 0
            row(type_hw="A", pn="6ES7131-6BH01-0BA0", slot="-K10", bit="I0.0"),
            row(type_hw="A", pn="6ES7131-6BH01-0BA0", slot="-K10", bit="I0.1"),
            # card 2: F-DI with DTD params -> I start byte 4
            row(type_hw="A", pn="6ES7136-6BA01-0CA0", slot="-K11", bit="I4.0"),
            # card 3: a DQ output -> Q start byte 2
            row(type_hw="A", pn="6ES7131-6BH01-0BA0", slot="-K12", bit="Q2.0"),
        ]

        st = hardware.extract_stations(rows, dtd)
        check("3 station heads (Plc, PlcCardCm, IoDevice)",
              [s["Role"] for s in st] == ["Plc", "PlcCardCm", "IoDevice"], str([s["Role"] for s in st]))
        check("Model Id strips spaces (PlcCardCm)", st[1]["Model Id"] == "6GK7542-1AX00-0XE0")
        check("station fields (name/IP/PN/subnet/group)",
              st[2]["Station Name"] == "n0005-im" and st[2]["IP Address"] == "192.168.50.5"
              and st[2]["PN Number"] == "5" and st[2]["Subnet"] == "Subnet50" and st[2]["Group"] == "=S1")

        mod = hardware.extract_modules(rows, dtd)
        check("3 cards grouped by Slot", [m["Module Name"] for m in mod] == ["-K10", "-K11", "-K12"],
              str([m["Module Name"] for m in mod]))
        check("plug order sequential", [m["Slot"] for m in mod] == [1, 2, 3])
        check("I start byte = lowest input byte of the card", mod[0]["I Addr"] == 0 and mod[1]["I Addr"] == 4)
        check("Q start byte for output card", mod[2]["Q Addr"] == 2 and mod[2]["I Addr"] == "")
        check("card gets DTD model default params", mod[1]["Custom Parameters"] == "Ch(0-7).Failsafe_DiscrepancyTime=100")
        check("cards belong to the IoDevice station", all(m["Station Name"] == "n0005-im" for m in mod))

        hardware.write_stations(st, tmp)
        hardware.write_modules(mod, tmp)
        with open(os.path.join(tmp, "Hardware", "Stations.csv"), encoding="utf-8-sig") as f:
            head = f.readline().strip()
        check("Stations.csv format-2 header", head == "#!format=2")

        print("ALL CHECKS PASS" if failures == 0 else f"{failures} CHECK(S) FAILED")
        raise SystemExit(0 if failures == 0 else 1)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
