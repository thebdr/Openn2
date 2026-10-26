"""C-043 refute round 1 (2026-10-26): the generic-hardware types' `mandatory_in` matching attacked with cases, taxonomy
words and wildcards; the SYCON handoff's card detection attacked with controller heads whose IP the 110 check lets
through. What broke and was fixed: a controller with an IP such as `1.2.3` (a dot, so no `ip_missing`) gave a card
without a network and every station with a real IP was dropped as "another network" - an INFO each, no FAIL
(`sycon_controller_ip` FAIL now, the stations exported unfiltered); two such heads merged into one card as if the
second were the redundant one (a head without a network is never merged). What held: the matching by id, by
taxonomy word, by `*`, in any case, nothing without a system; `network_of` on every malformed shape; the phase
sets and the Run-all plan of both types."""
from __future__ import annotations

import sys

from _harness import run, eq, ok
from pipeline5.phases.validation import iolist_checks
from pipeline5.systems import catalog
from pipeline5.systems.ipc_based.hilscher_syconnet.generic_hw.system import SYSTEM as SYCON
from pipeline5.systems.ipc_based.intervalzero_rtx import sycon_handoff as sycon
from pipeline5.systems.plc_based.siemens_s7.generic_hw.system import SYSTEM as TIA

SAFETY = catalog.by_id("siemens_s7_safety")

DTD = {"CIFX80-RE/ML": {"model_id": "CIFX80-RE/ML", "role": "controller", "catalog_item": "CIFX RE/PNM", "modules": "default", "gsdml": "", "comment": ""},
       "AL1202": {"model_id": "AL1202", "role": "slave", "catalog_item": "AL1202", "modules": "default", "gsdml": "", "comment": ""}}


def _col(canonical, mandatory_in):
    return {"canonical": canonical, "column": "A", "expected_header": canonical, "mandatory_in": tuple(mandatory_in)}


def _head(name, ip, part, slot, idn):
    return {"profinet_name": name, "profinet_ip": ip, "part_no": part, "slot": slot, "id_node": idn,
            "description_module": "X", "manufacturer": "M", "source_cell": name}


def test_mandatory_in_matches_id_taxonomy_and_star_in_any_case():
    colmap = [_col("part_no", ["*"]), _col("profinet_ip", ["SIEMENS_TIA_GENERIC_HW"]),
              _col("profinet_name", ["genericHARDWARE"]), _col("ce_area", ["plc_based"]), _col("ip_mask", ["IPC_Based"]),
              _col("nothing", ["nowhere"]), _col("blank", [])]
    tia = [m["canonical"] for m in iolist_checks.mandatory_for(TIA, colmap)]
    sycon_ = [m["canonical"] for m in iolist_checks.mandatory_for(SYCON, colmap)]
    safety = [m["canonical"] for m in iolist_checks.mandatory_for(SAFETY, colmap)]
    eq(tia, ["part_no", "profinet_ip", "profinet_name", "ce_area"], "TIA: star, its id, its taxonomy words")
    eq(sycon_, ["part_no", "profinet_name", "ip_mask"], "SYCON: star, GenericHardware, IPC_Based")
    eq(safety, ["part_no", "ce_area"], "the safety system: the star, and PLC_Based names every PLC-based system - a taxonomy word is a family")
    eq(iolist_checks.mandatory_for(None, colmap), [], "no system, nothing mandatory")


def test_network_of_refuses_every_malformed_shape():
    for bad in ("1.2.3", "a.b.c.d", "192.168.1.1/24", "", None, "192.168.1.1.1", "1.2.3.x"):
        eq(sycon.network_of(bad), None, repr(bad))
    eq(sycon.network_of(" 192.168.1.7 "), (192, 168, 1, 0), "spaces around the address are not a malformation")
    eq(sycon.network_of("192.168.1.7", "255.255.0.0"), (192, 168, 0, 0))


def test_a_controller_without_a_usable_ip_is_a_fail_not_a_silent_empty_project():
    rows = [_head("n0001-ctrl", "1.2.3", "CIFX 80-RE/ML", "-K1", "1"),
            _head("n0005-a", "192.168.1.5", "AL1202", "-K5", "5"),
            _head("n0006-b", "192.168.1.6", "AL1202", "-K6", "6")]
    stations, _m, findings = sycon.build(rows, DTD)
    kinds = [(f.type, f.severity) for f in findings]
    ok(("sycon_controller_ip", "FAIL") in kinds, f"a FAIL names the controller's IP (got {kinds})")
    ok(("sycon_other_network", "INFO") not in kinds, "the stations are not dropped as another network")
    eq([s["station_name"] for s in stations], ["n0001-ctrl", "n0005-a", "n0006-b"], "exported unfiltered, for the FAIL to be read")


def test_two_heads_without_a_network_are_two_cards_not_one_redundant_pair():
    rows = [_head("n0001-a", "1.2.3", "CIFX 80-RE/ML", "-K1", "1"), _head("n0001-b", "x", "CIFX 80-RE/ML", "-K2", "1"),
            _head("n0001-c", "192.168.4.1", "CIFX 80-RE/ML", "-K3", "1"), _head("n0001-d", "192.168.4.1", "CIFX 80-RE/ML", "-K4", "1")]
    cards = sycon.cards_of(rows, DTD)
    eq([(c["card"], c["name"], c["net"]) for c in cards], [(1, "n0001-a", None), (2, "n0001-b", None), (3, "n0001-c", (192, 168, 4, 0))],
       "the two broken heads stand alone; the fourth is the redundant card of the third")


def test_the_generic_plans_stay_validation_then_hardware():
    for s in (TIA, SYCON):
        eq(tuple(s.phases.run_order()), (100, 700), s.id)
        eq([p.number for p in s.phases.phases], [0, 100, 700], s.id)
    ok(len(SAFETY.phases.phases) > 3, "the safety system keeps its full plan")


TESTS = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]

if __name__ == "__main__":
    sys.exit(run("C-043 refute round 1", TESTS))
