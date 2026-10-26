"""The device-types database's module and catalog cells of 2026-10-26 (user: "pnpn couplers updated ... 4[*OUT 128 Byte]
| 4[*IN 128 Byte] - 4 is a multiplier (4 modules of the [] type, which is to be set verbatim); | is the separator"):
`N[text]` expands to N module rows in both the plain and the per-connector Fixed Modules cell; the Catalog Item cell
takes the per-connector form too, so an X1-side coupler head takes the catalog's X1 entry; the shipped database
reads with eight coupler modules a side and the switches at V4.3."""
from __future__ import annotations

import os
import sys
import tempfile

from _harness import run, eq, ok, raises
from pipeline5.systems.ipc_based.intervalzero_rtx import sycon_handoff as sycon

COUPLER = "6ES7158-3AD10-0XA0"


def _head(name, ip, part, slot, idn, connector=""):
    return {"profinet_name": name, "profinet_ip": ip, "part_no": part, "slot": slot, "id_node": idn, "connector": connector,
            "description_module": "X", "manufacturer": "M", "source_cell": name}


def test_module_items_expand_multipliers_verbatim():
    eq(sycon.module_items("4[*OUT 128 Byte] | 4[*IN 128 Byte]"), ["*OUT 128 Byte"] * 4 + ["*IN 128 Byte"] * 4)
    eq(sycon.module_items("IN 0016 | OUT 0012"), ["IN 0016", "OUT 0012"], "the old form unchanged")
    eq(sycon.module_items(" 2 [ A B ] |C| 1[D]"), [" A B ", " A B ", "C", "D"], "the bracketed text verbatim, a plain item stripped")
    eq(sycon.module_items("[X]"), ["[X]"], "brackets without a multiplier are text")
    eq(sycon.module_items(""), [])
    raises(ValueError, lambda: sycon.module_items("0[*IN 128 Byte]"))


def test_fixed_modules_per_connector_with_multipliers():
    cell = "X2: 4[*OUT 128 Byte] | 4[*IN 128 Byte]; X1: 4[*IN 128 Byte] | 4[*OUT 128 Byte]"
    fixed = sycon.fixed_modules(cell)
    eq(sorted(fixed), ["X1", "X2"])
    eq(fixed["X2"], ["*OUT 128 Byte"] * 4 + ["*IN 128 Byte"] * 4)
    eq(fixed["X1"], ["*IN 128 Byte"] * 4 + ["*OUT 128 Byte"] * 4)
    eq(sycon.by_connector("PN/PN Coupler X2 [DAP X2 V4.2]"), None, "a plain catalog item is not per connector")
    eq(sycon.by_connector("X2: PN/PN Coupler X2 [DAP X2 V4.2]; X1: PN/PN Coupler X1 [DAP X1 V4.2]"),
       {"X2": "PN/PN Coupler X2 [DAP X2 V4.2]", "X1": "PN/PN Coupler X1 [DAP X1 V4.2]"})


def test_the_catalog_item_follows_the_connector_and_the_modules_too():
    with tempfile.TemporaryDirectory() as d:
        dtd = os.path.join(d, "SyconDeviceTypesDatabase.csv")
        with open(dtd, "w", encoding="utf-8", newline="") as f:
            f.write("CIFX 80-RE/ML,controller,CIFX RE/PNM,default,,\r\n"
                    "%s,slave,X2: PN/PN Coupler X2 [DAP X2 V4.2]; X1: PN/PN Coupler X1 [DAP X1 V4.2],fixed,GSDML-V2.35-Siemens-PNPNIOC-20200924.xml,coupler,variable,"
                    "X2: 4[*OUT 128 Byte] | 4[*IN 128 Byte]; X1: 4[*IN 128 Byte] | 4[*OUT 128 Byte],4=0\r\n" % COUPLER)
        db = sycon.load_dtd(dtd)
    rows = [_head("n0001-ctrl", "192.168.1.1", "CIFX 80-RE/ML", "-K1", "1"),
            _head("n0006-x2", "192.168.1.6", COUPLER, "-K6", "6", connector="X2"),
            _head("n0007-x1", "192.168.1.7", COUPLER, "-K7", "7", connector="x1"),
            _head("n0008-none", "192.168.1.8", COUPLER, "-K8", "8")]
    stations, modules, findings = sycon.build(rows, db)
    eq([(s["station_name"], s["catalog_item"]) for s in stations[1:]], [
        ("n0006-x2", "PN/PN Coupler X2 [DAP X2 V4.2]"), ("n0007-x1", "PN/PN Coupler X1 [DAP X1 V4.2]"),
        ("n0008-none", "PN/PN Coupler X2 [DAP X2 V4.2]")], "the row's connector picks the entry; none: the first, with a WARN")
    by_station = {}
    for m in modules:
        by_station.setdefault(m["station_name"], []).append((m["slot"], m["subslot"], m["module_text"]))
    eq([t for s, sub, t in by_station["n0006-x2"] if not sub], ["*OUT 128 Byte"] * 4 + ["*IN 128 Byte"] * 4)
    eq([s for s, sub, t in by_station["n0006-x2"] if not sub], [str(n) for n in range(1, 9)], "slots 1..8")
    eq([t for s, sub, t in by_station["n0007-x1"] if not sub], ["*IN 128 Byte"] * 4 + ["*OUT 128 Byte"] * 4, "X1 mirrored")
    eq(by_station["n0006-x2"][0], ("0", "1", ""), "the DAP parameters row first")
    warns = [f for f in findings if f.type == "sycon_connector_unknown"]
    eq(len(warns), 2, "the connector-less head: no catalog entry and no modules for it, one WARN each")
    ok("n0008-none" in warns[0].detail and "taken" in warns[0].detail, warns[0].detail)
    ok(not [t for s, sub, t in by_station.get("n0008-none", []) if not sub], "no modules for a connector-less coupler")


def test_the_shipped_database_reads_as_the_user_set_it():
    db = sycon.load_dtd()
    coupler = db[COUPLER]
    eq(coupler["fixed_modules"]["X2"], ["*OUT 128 Byte"] * 4 + ["*IN 128 Byte"] * 4)
    eq(coupler["fixed_modules"]["X1"], ["*IN 128 Byte"] * 4 + ["*OUT 128 Byte"] * 4)
    eq(sycon.by_connector(coupler["catalog_item"]), {"X2": "PN/PN Coupler X2 [DAP X2 V4.2]", "X1": "PN/PN Coupler X1 [DAP X1 V4.2]"})
    for model, item in (("6GK5208-0BA00-2AC2", "SCALANCE XC208 V4.3"), ("6GK5206-2BS00-2AC2", "SCALANCE XC206-2 SFP V4.3"),
                        ("6GK5216-4BS00-2AC2", "SCALANCE XC216-4C V4.3")):
        eq(db[model]["catalog_item"], item, "the catalog's V4.3 entry (user 2026-10-26)")
        eq(db[model]["gsdml"], "GSDML-V2.45-Siemens-002A-SCALANCE_XC200-20260302.xml")
    ok(not [m for m, rec in db.items() if "V4.4" in rec["catalog_item"]], "no catalog item names V4.4 any more")


TESTS = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]

if __name__ == "__main__":
    sys.exit(run("the fixed-modules multiplier and the per-connector catalog item", TESTS))
