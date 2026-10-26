"""C-044 refute round 1 (2026-10-26), the PL5 side of the production folder: `project()` asked for a card the list
does not have, the symbolic-name rule on odd IPs and texts, the card folder names. What broke and was fixed: a
`project(card=3)` on a two-card list wrote `HilscherIOCard3/SyconNetProjectInterface/` with an empty table beside its
`sycon_no_card` FAIL - a stray card folder the GUI then showed as broken (the FAIL alone now, nothing written). What
held: the folder names, the symbolic label `nnn[_text]` on a three-digit octet, without an IP, without a text, with
spaces squeezed; the manufacturer key for a head without a Part No."""
from __future__ import annotations

import os
import sys
import tempfile

from _harness import run, eq, ok
from pipeline5.systems.ipc_based.intervalzero_rtx import sycon_handoff as sycon


def _head(name, ip, part, slot, idn, **more):
    row = {"profinet_name": name, "profinet_ip": ip, "part_no": part, "slot": slot, "id_node": idn,
           "description_module": "X", "manufacturer": "M", "source_cell": name}
    row.update(more)
    return row


def test_a_card_the_list_does_not_have_writes_no_folder():
    rows = [_head("n0001-a", "192.168.2.1", "CIFX 80-RE/ML", "-K1", "1"), _head("n0001-b", "192.168.3.1", "CIFX 80-RE/ML", "-K2", "1")]
    with tempfile.TemporaryDirectory() as d:
        dtd = os.path.join(d, "SyconDeviceTypesDatabase.csv")
        with open(dtd, "w", encoding="utf-8", newline="") as f:
            f.write("CIFX 80-RE/ML,controller,CIFX RE/PNM,default,,\r\n")
        res = sycon.project(rows, os.path.join(d, "PRODUCTION"), dtd, card=3)
        eq([f.type for f in res["findings"]], ["sycon_no_card"])
        ok(not os.path.exists(os.path.join(d, "PRODUCTION", "HilscherIOCard3")), "no stray card folder")
        eq(res["cards"][0]["dir"], "")
        both = sycon.project(rows, os.path.join(d, "ALL"), dtd)
        eq(sorted(os.listdir(os.path.join(d, "ALL"))), ["HilscherIOCard1", "HilscherIOCard2"], "one folder per card, named for the sorter PC")
        for n in (1, 2):
            ok(os.path.isfile(os.path.join(d, "ALL", "HilscherIOCard%d" % n, "SyconNetProjectInterface", "SyconStations.csv")))
        eq([c["controller"] for c in both["cards"]], ["n0001-a", "n0001-b"])


def test_the_symbolic_label_on_odd_ips_and_texts():
    row = {"functional_unit": "=TRIB", "location": "-CA01-AEC1", "desc_l1b": "  SORTER   LOWER ", "description_module": "x"}
    eq(sycon.symbolic_name("fld", row, "192.168.1.88"), "088_=TRIB-CA01")
    eq(sycon.symbolic_name("default", row, "192.168.1.7"), "007")
    eq(sycon.symbolic_name("fld", row, "10.0.0.300"), "300_=TRIB-CA01", "a three-digit octet keeps its digits")
    eq(sycon.symbolic_name("fld", row, ""), "=TRIB-CA01", "no IP: the text alone")
    eq(sycon.symbolic_name("fld", row, "1.2.3"), "=TRIB-CA01", "a malformed IP: the text alone")
    eq(sycon.symbolic_name("variable", row, "192.168.1.5"), "005_SORTER LOWER", "the variable's spaces squeezed")
    eq(sycon.symbolic_name("default", row, ""), "", "nothing to say")
    eq(sycon.symbolic_name("nonsense", row, "192.168.1.5"), "005", "an unknown rule gives the node alone")


def test_a_head_without_a_part_no_is_keyed_by_its_manufacturer():
    dtd = {"VITRONIC": {"model_id": "VITRONIC", "role": "slave", "catalog_item": "Anybus Communicator", "modules": "fixed",
                        "gsdml": "", "comment": "", "fixed_modules": ["IN 0064", "OUT 0064"]}}
    model, by_manufacturer = sycon.head_model(_head("n0090-cam", "192.168.1.90", "", "-K9", "90", manufacturer="Vitronic"), dtd)
    eq((model.upper(), by_manufacturer), ("VITRONIC", True))
    model, by_manufacturer = sycon.head_model(_head("n0090-cam", "192.168.1.90", "", "-K9", "90", manufacturer="Nobody"), dtd)
    eq((model, by_manufacturer), ("", False), "an unknown manufacturer keys nothing")


TESTS = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]

if __name__ == "__main__":
    sys.exit(run("C-044 refute round 1 (PL5)", TESTS))
