"""The SCALANCE XC216-4C's configurable ports (user 2026-11-02: "192.168.1.10: all 4 ports SFP; all the others: 1st port
SFP, the others RJ45"): the database row's ports per node (`n0010: 4[SFP 991-1 A]; *: 1[SFP 991-1 A] | 3[RJ45 1 GBit]` -
the main cabinet's switch is node 10 in both sorters, 192.168.1.10 lower, 192.168.6.10 upper), an I/O List row under a
switch overriding it, a list of the wrong length WARNed, a malformed cell refused by the loader."""
from __future__ import annotations

import os
import sys
import tempfile

from _harness import run, eq, ok, raises
from pipeline5.systems.ipc_based.intervalzero_rtx import sycon_handoff as sycon

XC216 = "6GK5216-4BS00-2AC2"
SFP, RJ45 = "SFP 991-1 A", "RJ45 1 GBit"


def _head(name, ip, part, slot, idn):
    return {"profinet_name": name, "profinet_ip": ip, "part_no": part, "slot": slot, "id_node": idn,
            "description_module": "SWITCH", "manufacturer": "SIEMENS", "source_cell": name}


def _ports(modules, station):
    return [(m["subslot"], m["module_text"], m["module_id"]) for m in modules
            if m["station_name"] == station and m["slot"] == "0" and m["subslot"] not in ("1", "32768")]


ROWS = [_head("n0001-trih-aec01-K22101.1", "192.168.6.1", "CIFX 80-RE/ML", "-K22101.1", "1"),
        _head("n0010-trih-aec01-K26501", "192.168.6.10", XC216, "-K26501", "10"),
        _head("n0015-trih-ae04-K26501", "192.168.6.15", XC216, "-K26501", "15")]


def test_node_keys():
    cell = "n0010: 4[SFP 991-1 A]; *: 1[SFP 991-1 A] | 3[RJ45 1 GBit]"
    eq(sycon.by_node(cell), {"n0010": "4[SFP 991-1 A]", "*": "1[SFP 991-1 A] | 3[RJ45 1 GBit]"})
    eq(sycon.for_node(cell, "n0010-trih-aec01-K26501"), "4[SFP 991-1 A]")
    eq(sycon.for_node(cell, "N0010-TRIB-AEC01-K26501"), "4[SFP 991-1 A]", "any case")
    eq(sycon.for_node(cell, "n0015-trih-ae04-K26501"), "1[SFP 991-1 A] | 3[RJ45 1 GBit]")
    eq(sycon.for_node("n0010: 4[X]", "n0015-a"), "", "no `*`: nothing for another node")
    eq(sycon.by_node("4[SFP 991-1 A]"), None)
    eq(sycon.for_node("4[SFP 991-1 A]", "n0015-a"), "4[SFP 991-1 A]", "a plain cell for every node")


def test_the_shipped_database_gives_the_hub_four_sfp_and_the_others_one():
    db = sycon.load_dtd()
    eq(db[XC216]["ports"], "n0010: 4[SFP 991-1 A]; *: 1[SFP 991-1 A] | 3[RJ45 1 GBit]")
    eq(db[XC216]["fixed_modules"], [], "a switch's column 8 is its ports, never modules")
    _s, modules, findings = sycon.build(ROWS, db)
    eq(_ports(modules, "n0010-trih-aec01-K26501"), [(str(32768 + n), SFP, "6GK5991-1AD00-8GA0") for n in (1, 2, 3, 4)])
    eq(_ports(modules, "n0015-trih-ae04-K26501"), [("32769", SFP, "6GK5991-1AD00-8GA0"), ("32770", RJ45, ""),
                                                  ("32771", RJ45, ""), ("32772", RJ45, "")])
    ok(not [f for f in findings if f.severity in ("WARN", "FAIL")], [(f.type, f.detail) for f in findings])


def test_an_iolist_row_under_a_switch_overrides_and_a_wrong_length_is_warned():
    db = sycon.load_dtd()
    rows = ROWS[:2] + [{"desc_l1": "2[SFP 991-1 A] | 2[RJ45 1 GBit]", "source_cell": "R1.S1.C1!O14"}] + ROWS[2:] + [
        {"desc_l1": "2[SFP 991-1 A]", "source_cell": "R1.S1.C1!O16"}]
    _s, modules, findings = sycon.build(rows, db)
    eq([t for _sub, t, _id in _ports(modules, "n0010-trih-aec01-K26501")], [SFP, SFP, RJ45, RJ45], "the row, not the database")
    eq([t for _sub, t, _id in _ports(modules, "n0015-trih-ae04-K26501")], [SFP, SFP], "the two the row names")
    kinds = [(f.type, f.severity) for f in findings]
    ok(("sycon_port_list_length", "WARN") in kinds and ("sycon_module_list_ignored", "WARN") not in kinds, kinds)
    ok(all("I/O List row" in m["comment"] for m in modules if m["station_name"].startswith("n0010") and m["subslot"] not in ("32768",)),
       "the ports' comment names their source")


def test_a_malformed_ports_cell_is_refused():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "SyconDeviceTypesDatabase.csv")
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write("CIFX 80-RE/ML,controller,CIFX RE/PNM,default,,\r\n"
                    "%s,slave,SCALANCE XC216-4C V4.3,scalance-pnio,G.xml,switch,fld,n0010: SFP 991-1 A\r\n" % XC216)
        raises(ValueError, lambda: sycon.load_dtd(path))


TESTS = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]

if __name__ == "__main__":
    sys.exit(run("the SCALANCE configurable ports", TESTS))
