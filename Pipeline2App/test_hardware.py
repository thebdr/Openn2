#!/usr/bin/env python3
"""Synthetic test for hardware extract() (Stations + Modules). Run: python test_hardware.py"""
from pipeline2.core import config, hardware

failures = 0


def check(name, ok, detail=""):
    global failures
    print(("PASS  " if ok else "FAIL  ") + name + (f"  [{detail}]" if detail else ""))
    if not ok:
        failures += 1


def row(script="", type_hw="", pn="", slot="", bit="", fu="=S1", pname="", idn="", ag=""):
    return {"script_type": script, "type_hw": type_hw, "part_no": pn, "slot": slot, "bit": bit,
            "functional_unit": fu, "profinet_name": pname, "id_node": idn, "hardware_params": ag,
            "_source_row": 0}


def rec(ident, params="", by_type="", io_addr="", comment="C", parent=None):
    return {"model_id": ident, "dev_type": "", "order": "", "comment": comment, "params": params,
            "params_by_type": config.parse_params_by_type(by_type), "io_addr_params": io_addr, "parent": parent}


def main():
    by_id = {
        "6ES7518-4FP00-0AB0": rec("6ES7518-4FP00-0AB0", comment="CPU"),
        "6ES7155-6AU01-0BN0": rec("6ES7155-6AU01-0BN0", comment="IM155"),
        "6ES7131-6BH01-0BA0": rec("6ES7131-6BH01-0BA0", comment="DI"),
        "6ES7136-6BA00-0CA0": rec("6ES7136-6BA00-0CA0", comment="F-DI",
                                  by_type="<B1/2>Ch(#).Failsafe_DiscrepancyTime=450 | Ch(#).Failsafe_SensorEvaluation=0<B1/2>"),
        "55556": rec("55556", comment="MVK"),
        "<55556>:DEFAULTCARD": rec("<55556>:DefaultCard", params="Failsafe_FDestinationAddress=IP[3]",
                                   comment="MVK card", parent="55556"),
        "LU1": rec("LU1", io_addr="Item(0).Addr(0).StartAddress = %I% | Item(1).Addr(0).StartAddress = %I%+10",
                   comment="LUMBERG"),
    }
    default_cards = {"55556": ["<55556>:DefaultCard"]}
    dtd = {"by_id": by_id, "default_cards": default_cards}

    rows = [
        row(script="PLC", pn="6ES7518-4FP00-0AB0", pname="n01-plc"),
        row(type_hw="PW", pn="6GK5208", pname="n10-sw"),                       # not in DTD -> skipped
        row(type_hw="PA", pn="6ES7155-6AU01-0BN0", slot="-K65001", pname="n05-im"),  # IoDevice head (tag -K65001)
        row(type_hw="A", pn="6ES7131-6BH01-0BA0", slot="-K10", bit="I0.0"),    # card -K10 DI
        row(type_hw="A", pn="6ES7131-6BH01-0BA0", slot="-K10", bit="I0.1"),
        row(type_hw="A", pn="6ES7131-6BH01-0BA0", slot="-K11", bit="I4.0"),    # card -K11 DI (model same -> no PG)
        row(script="B1/2", pn="6ES7136-6BA00-0CA0", slot="-K12", bit="I20.1",  # card -K12 F-DI, B1/2 at ch1
            ag="PotentialGroup=1"),                                            #   slot 2+ PG comes from col AG
        # Murrelektronik with a default card and a LUMBERG with auto-plugged card
        row(type_hw="PA", pn="55556", slot="-XN1", pname="n13-mvk"),
        row(type_hw="PA", pn="LU1", slot="-XNS1", pname="n31-lum", ag=""),
        row(bit="I920.0", slot="-XNS1"),   # LUMBERG signal on its own tag -> auto-plugged, skipped
        row(bit="I921.7", slot="-XNS1"),
    ]

    st, mod, _messages = hardware.extract(rows, dtd)

    names = [s["Station Name"] for s in st]
    check("switch (not in DTD) excluded", "n10-sw" not in names, str(names))
    check("PN empty + Group suffix", st[0]["PN Number"] == "" and st[0]["Group"] == "=S1_IODevices")
    lum = next(s for s in st if s["Station Name"] == "n31-lum")
    check("LUMBERG %I% resolved (920, +10=930)",
          lum["Custom Parameters"] == "Item(0).Addr(0).StartAddress = 920 | Item(1).Addr(0).StartAddress = 930",
          lum["Custom Parameters"])

    im = [m for m in mod if m["Station Name"] == "n05-im"]
    check("cards grouped (-K10,-K11,-K12), auto/own-tag excluded",
          [m["Module Name"] for m in im] == ["-K10", "-K11", "-K12"], str([m["Module Name"] for m in im]))
    check("I Addr = Q Addr = start byte", im[0]["I Addr"] == 0 and im[0]["Q Addr"] == 0 and im[1]["I Addr"] == 4)
    check("PotentialGroup=1 on the first card only; slots 2+ come from col AG",
          im[0]["Custom Parameters"] == "PotentialGroup=1"      # first card auto-starts a group
          and im[1]["Custom Parameters"] == ""                  # slot 2, no col AG -> none
          and "PotentialGroup=1" in im[2]["Custom Parameters"], # slot 3 PG supplied via col AG
          im[1]["Custom Parameters"] + " | " + im[2]["Custom Parameters"])
    check("by-type expanded Ch(#)->Ch(channel) for B1/2 at ch1",
          "Ch(1).Failsafe_DiscrepancyTime=450" in im[2]["Custom Parameters"], im[2]["Custom Parameters"])
    check("module comment from DTD", im[0]["Comment"] == "DI")

    mvk = [m for m in mod if m["Station Name"] == "n13-mvk"]
    check("default card <55556>:DefaultCard emitted as a module (DTD col-5 params applied by Open2App, not here)",
          len(mvk) == 1 and mvk[0]["Model Id"] == "<55556>:DefaultCard"
          and mvk[0]["Custom Parameters"] == "", str(mvk))

    lummod = [m for m in mod if m["Station Name"] == "n31-lum"]
    check("LUMBERG auto-plugged card -> no module row", lummod == [], str(lummod))

    print("ALL CHECKS PASS" if failures == 0 else f"{failures} CHECK(S) FAILED")
    raise SystemExit(0 if failures == 0 else 1)


if __name__ == "__main__":
    main()
