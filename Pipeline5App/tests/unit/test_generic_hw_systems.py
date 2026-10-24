"""The two generic-hardware project types (user 2026-10-24: validation + hardware generation only): their
registration, their phase sets (0, 100, 700 - no fill, staging button, interfaces, data blocks, diagnosis,
software or reporting), their Run-all plan, their handlers, their names, and the SYCON layout."""
from __future__ import annotations

import sys

from _harness import run, eq, ok
from pipeline5.language import i18n
from pipeline5.systems import catalog, generic_hw
from pipeline5.systems.ipc_based.hilscher_syconnet.generic_hw.system import SYSTEM as SYCON
from pipeline5.systems.plc_based.siemens_s7.generic_hw.system import SYSTEM as TIA

GENERIC = (TIA, SYCON)


def test_registered_and_named():
    for s in GENERIC:
        ok(catalog.by_id(s.id) is s, f"{s.id} registered")
        ok(i18n.tr(s.name_key, "en") != s.name_key and i18n.tr(s.name_key, "it") != s.name_key, f"{s.id} named in EN and IT")
    eq(TIA.id, "siemens_tia_generic_hw")
    eq(SYCON.id, "hilscher_syconnet_generic_hw")
    eq(TIA.taxonomy[-1], "GenericHardware")
    eq(SYCON.taxonomy, ("IPC_Based", "HilscherSYCONnet", "GenericHardware"))


def test_phase_sets_are_validation_and_hardware_only():
    for s in GENERIC:
        numbers = [p.number for p in s.phases.phases]
        eq(numbers, [0, 100, 700], f"{s.id}: Run-all, validation, hardware - nothing else")
        eq(s.phases.run_plan, (100, 700), f"{s.id}: the documents judged first, then the hardware")
        for p in s.phases.phases:
            if p.number:
                ok(p.handler in s.handlers, f"{s.id}: phase {p.number} handler {p.handler!r} resolves")
        subs = {sub.number: sub for p in s.phases.phases for sub in p.subs}
        eq(subs[110].kind, "action")
        eq(subs[710].kind, "action")
        eq(subs[720].kind, "action")
        eq(subs[740].kind, "open")
        eq(subs[740].opens, "hardware")
        for sub in subs.values():
            ok(i18n.tr(sub.label_key, "en") != sub.label_key, f"{s.id}: sub {sub.number} labelled")
        ok(not s.capabilities.needs_ce_matrix and not s.capabilities.needs_diagnosis_blocks, f"{s.id}: no C&E, no diagnosis")


def test_handlers_are_the_shared_chapters():
    eq(TIA.handlers["validation"], generic_hw.run_validation)
    eq(SYCON.handlers["validation"], generic_hw.run_validation)
    eq(TIA.handlers["hardware"], generic_hw.run_hardware_tia)
    eq(SYCON.handlers["hardware"], generic_hw.run_hardware_sycon)


def test_sycon_layout_points_at_the_handoff_folder():
    dirs = SYCON.output_layout.dirs()
    ok(dirs["hardware"].replace("/", "\\").endswith("\\PRODUCTION"), dirs["hardware"])
    eq(SYCON.output_layout.delivery_dirs(None), dirs)


def test_siemens_safety_untouched():
    safety = catalog.by_id("siemens_s7_safety")
    eq(safety.phases.run_plan, (300, 400, 500, 600, 700, 800, 900, 100), "the safety system's plan as before")


if __name__ == "__main__":
    sys.exit(run("generic_hw_systems", [
        ("registered_and_named", test_registered_and_named),
        ("phase_sets_are_validation_and_hardware_only", test_phase_sets_are_validation_and_hardware_only),
        ("handlers_are_the_shared_chapters", test_handlers_are_the_shared_chapters),
        ("sycon_layout_points_at_the_handoff_folder", test_sycon_layout_points_at_the_handoff_folder),
        ("siemens_safety_untouched", test_siemens_safety_untouched),
    ]))
