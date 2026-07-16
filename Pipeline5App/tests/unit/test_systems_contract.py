"""The system-type plugin contract + catalog (pipeline5.systems) - the first plugin-seam tests."""
from _harness import run, eq, ok, raises

from pipeline5.systems import catalog
from pipeline5.systems.system_contract import (
    BuilderRegistry,
    System,
    SystemCapabilities,
)


def _stub_system(sid="stub_system", **kw):
    return System(id=sid, name_key=f"sys_{sid}", taxonomy=("Test", "Stub", sid), **kw)


def test_builder_registry_isolation():
    """Two registries must not leak into each other - the PL4 module-global is dead."""
    a, b = BuilderRegistry(), BuilderRegistry()

    @a.builds("01_Only In A", emit="fc_xml")
    def build_a(_db):  # noqa: ANN001
        return None

    eq(sorted(a.registry()), ["01_Only In A"], "a holds its builder")
    eq(b.registry(), {}, "b saw nothing")
    eq(a.emit_kind("01_Only In A"), "fc_xml", "declared kind")
    eq(a.emit_kind("never registered"), "csv", "undeclared -> csv default")
    ok(a.registry()["01_Only In A"] is build_a, "decorator returns the function unchanged")

    a.clear()
    eq(a.registry(), {}, "clear() drops registrations")
    eq(a.emit_kind("01_Only In A"), "csv", "clear() drops emit kinds too")


def test_system_descriptor_validates():
    s = _stub_system()
    eq(s.capabilities, SystemCapabilities(), "capability flags default to False")
    ok(not s.capabilities.needs_ce_matrix and not s.capabilities.needs_diagnosis_blocks)
    ok(isinstance(s.builders, BuilderRegistry), "each System gets its OWN registry instance")
    ok(s.builders is not _stub_system("other").builders, "default registries are per-instance")
    raises(ValueError, lambda: System(id="", name_key="k", taxonomy=("T",)))
    raises(ValueError, lambda: System(id="  ", name_key="k", taxonomy=("T",)))
    raises(ValueError, lambda: System(id="x", name_key="k", taxonomy=()))


def test_system_is_frozen():
    s = _stub_system()
    def mutate():
        s.id = "renamed"
    raises(Exception, mutate)  # dataclasses.FrozenInstanceError


def test_catalog_planned_rows_greyed():
    """With nothing registered, every catalog row is a greyed PLANNED roadmap row."""
    rows = catalog.catalog()
    eq(len(rows), len(catalog.PLANNED), "empty registry -> exactly the PLANNED rows")
    ok(all(available is False for _, _, available in rows), "all greyed")
    ids = [r[0] for r in rows]
    ok("siemens_s7_safety" in ids and "intervalzero_rtx_sorter" in ids, "taxonomy ids present")
    eq(catalog.by_id("siemens_s7_safety"), None, "planned-but-unregistered resolves to None")
    eq(catalog.by_id("no_such_system"), None, "unknown resolves to None")


def test_catalog_registration_flips_availability():
    """Registering a system makes it available and supersedes its PLANNED row (the
    availability-from-registry mechanism the New-project dialog derives from)."""
    stub = _stub_system("siemens_s7_safety")
    original = catalog.ALL_SYSTEMS
    try:
        catalog.ALL_SYSTEMS = (stub,)
        rows = catalog.catalog()
        eq(rows[0], ("siemens_s7_safety", "sys_siemens_s7_safety", True), "registered row first + available")
        eq(len([r for r in rows if r[0] == "siemens_s7_safety"]), 1, "PLANNED row superseded, not doubled")
        eq(len(rows), len(catalog.PLANNED), "3 planned + 1 registered")
        ok(catalog.by_id("siemens_s7_safety") is stub, "by_id resolves the registered instance")
    finally:
        catalog.ALL_SYSTEMS = original


def test_catalog_duplicate_id_fails_loud():
    original = catalog.ALL_SYSTEMS
    try:
        catalog.ALL_SYSTEMS = (_stub_system("dup"), _stub_system("dup"))
        raises(ValueError, catalog._validate)
    finally:
        catalog.ALL_SYSTEMS = original


if __name__ == "__main__":
    import sys
    sys.exit(run("systems_contract", [
        ("builder_registry_isolation", test_builder_registry_isolation),
        ("system_descriptor_validates", test_system_descriptor_validates),
        ("system_is_frozen", test_system_is_frozen),
        ("catalog_planned_rows_greyed", test_catalog_planned_rows_greyed),
        ("catalog_registration_flips_availability", test_catalog_registration_flips_availability),
        ("catalog_duplicate_id_fails_loud", test_catalog_duplicate_id_fails_loud),
    ]))
