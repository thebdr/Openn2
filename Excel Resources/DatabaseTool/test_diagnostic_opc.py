#!/usr/bin/env python3
"""Synthetic test for diagnostic_opc (SCL fill) + diagnosis_rules. Uses the real template
and config/diagnosis_*.csv. Run: python test_diagnostic_opc.py"""
import sys
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import diagnostic_opc
import diagnosis_rules

failures = 0


def check(name, ok, detail=""):
    global failures
    print(("PASS  " if ok else "FAIL  ") + name + (f"  [{detail}]" if detail else ""))
    if not ok:
        failures += 1


def row(script, cab, bit, type_hw, dev="-X", tag="", nid="", nc="", pn="", subnet="",
        dlogic="", dbnames=None, fu="=S1", loc="+MS1.CC1", in_diag=True):
    return {
        "script_type": script, "type_hw": type_hw, "diag_cabinet": cab, "diag_bit": bit,
        "functional_unit": fu, "location": loc, "device": dev, "bit": "",
        "name_in_db": nid, "name_in_tagtable": tag, "normal_condition": nc,
        "profinet_name": pn, "subnet_name": subnet,
        "_type": {"in_diagnosis": in_diag, "diagnosis_logic": dlogic, "db_names": dbnames or []},
    }


def main():
    alarm0 = row("A", "001", "00", "A", dev="-F1", tag="ALARM ONE =S1+MS1.CC1-F1", nc="1")    # invert -> ML FALSE
    alarm0["bit"] = "I1.0"                                                                    # address -> resolves to pa_node
    pa_node = row("PA", "001", "01", "PA", pn="n0005-x", subnet="Subnet50", dlogic="mirror",
                  nid="FIELD BUS FAILURE", dbnames=["PROFINET_NODES_ALARM"])                  # mirror, DB-qual IN, node-level -> FL false
    pa_node["I_startByte"], pa_node["I_endByte"], pa_node["profinet_ip"] = 0, 20, "192.168.50.5"   # node covering alarm0
    db = [
        alarm0, pa_node,
        row("W", "001", "00", "W", dev="-W1", tag="WARN ONE", nc=""),                         # NoTristate warning
        row("A", "012", "00", "A", dev="-F12", tag="ALARM TWELVE", nc="1"),                   # tristate cabinet
        # encoder pair physically at PC1 (cabinet 009) but ASSIGNED to cabinet 014 (their
        # diag_cabinet); they occupy bits 00/01 there, so the rule-generated "Safety Encoder
        # Failure" must land in 014 at the next free bit (02) - NOT in PC1's 009.
        row("ENC1/2", "014", "00", "A", dev="-X81001", loc="+PC1.CC1", tag="ENC ONE HEALTHY", dlogic="invert"),
        row("ENC2/2", "014", "01", "A", dev="-X81001", loc="+PC1.CC1", tag="ENC TWO HEALTHY", dlogic="invert"),
    ]
    blocks = {
        1:  {"index": "001", "fld": "=S1+MS1.CC1", "template_type": "1"},   # AutoReset/NoTristate
        9:  {"index": "009", "fld": "=S1+PC1.CC1", "template_type": "1"},
        12: {"index": "012", "fld": "=S1+Field", "template_type": "2"},     # AutoReset/Tristate
        14: {"index": "014", "fld": "=S1+SafetyEncoders", "template_type": "2"},
    }

    logic_rows, logic_entries = diagnosis_rules.build_list_logic(db, blocks)
    entries = diagnostic_opc.io_entries(db) + logic_entries
    scl = diagnostic_opc.render_scl(db, blocks, entries)

    import re
    a1 = re.search(r'"S1\.CABINET001\.ALARM1"\(.*?\);', scl, re.S).group(0)   # the FB call, not the DiagnosticTags ref
    check("alarm IN = tag, ML invert(FALSE), FL = node PROFINET_ALARMS",
          'IN_00 := "ALARM ONE =S1+MS1.CC1-F1"' in a1 and "ML_00 := FALSE" in a1
          and 'FL_00 := "PROFINET_NODES_ALARM"."n0005-x 192.168.50.5"' in a1)
    check("PA(node) IN = DB-qualified, ML mirror(TRUE), FL = false (no self-filter)",
          'IN_01 := "PROFINET_NODES_ALARM"."FIELD BUS FAILURE"' in a1
          and "ML_01 := TRUE" in a1
          and "FL_01 := false" in a1)
    check("NoTristate alarm DWord = ALARM1", "Tristate_DW" not in a1)
    check("CabState instance = S1.CABINET001.STATE", '"S1.CABINET001.STATE"(' in scl)
    w1 = re.search(r'"S1\.CABINET001\.WARNING1"\(.*?\);', scl, re.S)
    check("NoTristate warning emitted (S1.CABINET001.WARNING1, ML mirror)",
          w1 is not None and "ML_00 := TRUE" in w1.group(0))

    a12 = re.search(r'"S1\.CABINET012\.ALARM1"\(.*?\);', scl, re.S).group(0)
    check("Tristate cabinet pairs the warning DWord",
          'Alarm_Warning_DW := "DiagnosticTags"."S1.CABINET012.ALARM1"' in a12
          and 'Tristate_DW => "DiagnosticTags"."S1.CABINET012.WARNING1"' in a12)

    check("unused channels removed (no IN_05 in cabinet 001 ALARM1)", "IN_05" not in a1)

    check("List_Logic rule lands in the encoders' cabinet (014) at next free bit (02)",
          len(logic_entries) == 1 and logic_entries[0]["cabinet"] == 14
          and logic_entries[0]["bit"] == 2
          and logic_entries[0]["in"] == '"04_SPEED"."Safety Encoder Failure =S1+PC1.CC1-X81001"')

    check("SCL is one FUNCTION", scl.count("FUNCTION") >= 1 and "END_FUNCTION" in scl)

    print("ALL CHECKS PASS" if failures == 0 else f"{failures} CHECK(S) FAILED")
    raise SystemExit(0 if failures == 0 else 1)


if __name__ == "__main__":
    main()
