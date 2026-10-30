"""A station's own module list in the I/O List (user 2026-10-26: "added new custom modules management: 4[*OUT 128 Byte]
| 4[*IN 128 Byte]"; 2026-10-30: "the couplers got a new submodule management" - the LOWER SORTER R1.4 puts it on the
row under a coupler's head, Column I, staged as `desc_l1`): the strict form, the list replacing the database's for
that station, the database's per connector for a station without one, a list under a policy that is not `fixed`
ignored with a WARN, a second list WARNed, an ordinary description never read as a list."""
from __future__ import annotations

import sys

from _harness import run, eq, ok
from pipeline5.systems.ipc_based.intervalzero_rtx import sycon_handoff as sycon

COUPLER = "6ES7158-3AD10-0XA0"
DTD = {
    "CIFX80-RE/ML": {"model_id": "CIFX80-RE/ML", "role": "controller", "catalog_item": "CIFX RE/PNM", "modules": "default", "gsdml": "", "comment": ""},
    COUPLER: {"model_id": COUPLER, "role": "slave", "modules": "fixed", "gsdml": "", "comment": "", "dap_parameters": "",
              "catalog_item": "X2: PN/PN Coupler X2 [DAP X2 V4.2]; X1: PN/PN Coupler X1 [DAP X1 V4.2]",
              "fixed_modules": {"X2": ["*OUT 128 Byte"] * 4 + ["*IN 128 Byte"] * 4, "X1": ["*IN 128 Byte"] * 4 + ["*OUT 128 Byte"] * 4}},
    "AL1202": {"model_id": "AL1202", "role": "slave", "catalog_item": "AL1202", "modules": "default", "gsdml": "", "comment": ""},
}


def _head(name, ip, part, slot, idn, connector=""):
    return {"profinet_name": name, "profinet_ip": ip, "part_no": part, "slot": slot, "id_node": idn, "connector": connector,
            "description_module": "PN/PN COUPLER", "desc_l1": "COUPLER FIELDBUS MODULE", "manufacturer": "SIEMENS", "source_cell": name}


def _list_row(text, cell):
    return {"desc_l1": text, "drawing": "8FVT_Q0011", "sheet": "355", "source_cell": cell}


def _modules(modules, station):
    return [m["module_text"] for m in modules if m["station_name"] == station and not m["subslot"]]


def test_the_strict_form():
    for text in ("2[*IN 128 Byte] | 2[*OUT 128 Byte]", "4[*OUT 128 Byte] | 4[*IN 128 Byte]", "1[IN 0016]", " 3 [ A ] |1[B]"):
        ok(sycon.is_module_list(text), text)
    for text in ("COUPLER FIELDBUS MODULE", "IN 0016 | OUT 0012", "SORTER (=TRIB) / INDUCTION LINES GR1 (=TRIB-AEC01)",
                 "2[*IN 128 Byte] | OUT 0012", "[*IN 128 Byte]", "2[a[b]]", "", None):
        ok(not sycon.is_module_list(text), repr(text))


def test_the_rows_list_replaces_the_databases_for_its_station():
    rows = [_head("n0001-ctrl", "192.168.1.1", "CIFX 80-RE/ML", "-K1", "1"),
            _head("n0006-trib-aec01-K24501", "192.168.1.6", COUPLER, "-K24501", "6", connector="X1"),
            _list_row("2[*IN 128 Byte] | 2[*OUT 128 Byte]", "R1.S1.C1!O6"),
            _head("n0004-tric-aec01-K25101", "192.168.1.4", COUPLER, "-K25101", "4", connector="X2"),
            _head("n0008-tric-aec01-K24501", "192.168.1.8", COUPLER, "-K24501", "8", connector="X2"),
            _list_row("4[*OUT 128 Byte] | 4[*IN 128 Byte]", "R1.S1.C1!O11"),
            _head("n0009-tric-aec01-K24601", "192.168.1.9", COUPLER, "-K24601", "9", connector="X1")]
    stations, modules, findings = sycon.build(rows, DTD)
    eq([(s["station_name"], s["catalog_item"]) for s in stations[1:]], [
        ("n0006-trib-aec01-K24501", "PN/PN Coupler X1 [DAP X1 V4.2]"), ("n0004-tric-aec01-K25101", "PN/PN Coupler X2 [DAP X2 V4.2]"),
        ("n0008-tric-aec01-K24501", "PN/PN Coupler X2 [DAP X2 V4.2]"), ("n0009-tric-aec01-K24601", "PN/PN Coupler X1 [DAP X1 V4.2]")])
    eq(_modules(modules, "n0006-trib-aec01-K24501"), ["*IN 128 Byte"] * 2 + ["*OUT 128 Byte"] * 2, "its own row")
    eq(_modules(modules, "n0008-tric-aec01-K24501"), ["*OUT 128 Byte"] * 4 + ["*IN 128 Byte"] * 4, "its own row")
    eq(_modules(modules, "n0004-tric-aec01-K25101"), DTD[COUPLER]["fixed_modules"]["X2"], "no row: the database's X2 list")
    eq(_modules(modules, "n0009-tric-aec01-K24601"), DTD[COUPLER]["fixed_modules"]["X1"], "no row: the database's X1 list")
    row6 = [m for m in modules if m["station_name"] == "n0006-trib-aec01-K24501" and not m["subslot"]]
    eq([m["slot"] for m in row6], ["1", "2", "3", "4"])
    ok(row6[0]["comment"] == "module of %s from the I/O List row R1.S1.C1!O6" % COUPLER, row6[0]["comment"])
    infos = [f for f in findings if f.type == "sycon_modules_from_iolist"]
    eq(len(infos), 2)
    ok(all(f.severity == "INFO" for f in infos) and "R1.S1.C1!O6" in infos[0].detail, infos[0].detail)


def test_a_list_under_another_policy_and_a_second_list_are_warned():
    rows = [_head("n0001-ctrl", "192.168.1.1", "CIFX 80-RE/ML", "-K1", "1"),
            _head("n0035-trib-x", "192.168.1.35", "AL1202", "-K1", "35"),
            _list_row("1[Something]", "R1.S1.C1!O20"),
            _head("n0006-trib-aec01-K24501", "192.168.1.6", COUPLER, "-K24501", "6", connector="X1"),
            _list_row("2[*IN 128 Byte] | 2[*OUT 128 Byte]", "R1.S1.C1!O6"),
            _list_row("1[*IN 128 Byte]", "R1.S1.C1!O7")]
    _s, modules, findings = sycon.build(rows, DTD)
    kinds = sorted((f.type, f.severity) for f in findings)
    ok(("sycon_module_list_ignored", "WARN") in kinds and ("sycon_module_list_twice", "WARN") in kinds, kinds)
    eq(_modules(modules, "n0035-trib-x"), [], "a default-policy station plugs nothing from a list")
    eq(_modules(modules, "n0006-trib-aec01-K24501"), ["*IN 128 Byte"] * 2 + ["*OUT 128 Byte"] * 2, "the first list")


def test_the_dap_record_oracle_follows_the_side():
    """2026-10-30: the coupler's record 1 ends with its GEO ID (1 on X1, 2 on X2): the shipped database names one
    oracle per side; the plain form still works."""
    db = sycon.load_dtd()
    eq(sycon.by_connector(db[COUPLER]["dap_parameters"]),
       {"X2": "4=0 | record:1=00 0C 00 02 00 00", "X1": "4=0 | record:1=00 0C 00 01 00 00"})
    rows = [_head("n0001-ctrl", "192.168.1.1", "CIFX 80-RE/ML", "-K1", "1"),
            _head("n0006-x1", "192.168.1.6", COUPLER, "-K24501", "6", connector="X1"),
            _head("n0008-x2", "192.168.1.8", COUPLER, "-K24502", "8", connector="x2"),
            _head("n0009-none", "192.168.1.9", COUPLER, "-K24601", "9")]
    _s, modules, _f = sycon.build(rows, db)
    dap = {m["station_name"]: m["parameters"] for m in modules if m["slot"] == "0" and m["subslot"] == "1"}
    eq(dap, {"n0006-x1": "4=0 | record:1=00 0C 00 01 00 00", "n0008-x2": "4=0 | record:1=00 0C 00 02 00 00",
             "n0009-none": "4=0 | record:1=00 0C 00 02 00 00"})
    eq(sycon.for_connector("4=0", {"connector": "X1"}), "4=0", "a plain cell for every side")


def test_an_ordinary_signal_row_is_not_a_list():
    rows = [_head("n0001-ctrl", "192.168.1.1", "CIFX 80-RE/ML", "-K1", "1"),
            _head("n0006-trib-aec01-K24501", "192.168.1.6", COUPLER, "-K24501", "6", connector="X2"),
            {"desc_l1": "SORTER RUNNING", "slot": "", "source_cell": "R1.S1.C1!O7"}]
    _s, modules, findings = sycon.build(rows, DTD)
    eq(_modules(modules, "n0006-trib-aec01-K24501"), DTD[COUPLER]["fixed_modules"]["X2"])
    ok(not [f for f in findings if f.type.startswith("sycon_module")], [f.type for f in findings])


TESTS = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]

if __name__ == "__main__":
    sys.exit(run("a station's module list in the I/O List", TESTS))
