"""The siemens_s7_safety System descriptor - the first registered plugin (step 3)."""
from _harness import run, eq, ok, raises

from pipeline5.phases.datablocks.generator import write_back
from pipeline5.systems import catalog
from pipeline5.systems.plc_based.siemens_s7.safety.system import SYSTEM
from pipeline5.systems.plc_based.siemens_s7.symbols import TiaSymbols


def test_descriptor_shape():
    eq(SYSTEM.id, "siemens_s7_safety", "the taxonomy id")
    eq(SYSTEM.taxonomy, ("PLC_Based", "SiemensS7", "Safety"), "the display tree")
    ok(SYSTEM.capabilities.needs_ce_matrix, "Safety uses the C&E matrix")
    ok(SYSTEM.capabilities.needs_diagnosis_blocks, "Safety uses the DiagnosisBlocks sheet")
    ok(catalog.by_id("siemens_s7_safety") is SYSTEM, "registered in the catalog")


def test_tia_symbols_round_trip():
    s = TiaSymbols()
    eq(s.binding("03_FDBACK", "Door Alarm [ =S1+A-K1 ]"), '"03_FDBACK"."Door Alarm [ =S1+A-K1 ]"')
    eq(s.quote("EMERGENCY_PushButtons"), '"EMERGENCY_PushButtons"')
    eq(s.parse_binding('"A"."B"'), ("A", "B"), "parse inverts binding")
    eq(s.parse_binding('no binding here'), None, "no match -> None")
    eq(s.parse_binding(""), None, "empty is safe")
    eq(s.find_bindings('x "A"."B" y "C"."D"'), [("A", "B"), ("C", "D")], "finds every ref in order")
    eq(s.find_bindings(None), [], "None is safe")


def test_emitters_declare_ready_kinds():
    ok("scl" in SYSTEM.emitters and "fc_xml" in SYSTEM.emitters and "fdback_xml" in SYSTEM.emitters,
       "the three READY kinds are declared")
    ok("csv" not in SYSTEM.emitters, "the CreationInfo csv default stays engine-internal until step 4")


def test_builders_proxy_reflects_module_registry():
    import pipeline5.phases.software_blocks._siemens_s7.builders  # noqa: F401  (registers on import)
    names = SYSTEM.builders.registry()
    ok("03_Zone Cumulative" in names, "the proxy sees the module registrations")
    eq(SYSTEM.builders.emit_kind("03_Zone Cumulative"), "fc_xml", "and their declared kinds")


def _member(source_row, seq, name):
    return {"source_row": source_row, "seq": seq, "name": name}


def test_write_back_binding_parity_with_and_without_system():
    """The system's symbol formatter must produce byte-identical bindings to the PL4 literal."""
    for system in (None, SYSTEM):
        r1, r2 = {"name_in_tagtable": ""}, {"name_in_tagtable": "Fire Alarm [ K9 ]"}
        global_dbs = {"07_DOOR": {"members": [_member(r1, 1, "Door Alarm [ K1 ]")]}}
        write_back([r1, r2], global_dbs, system=system)
        eq(r1["plc_binding"], '"07_DOOR"."Door Alarm [ K1 ]"', f"member binding (system={system})")
        eq(r2["plc_binding"], '"Fire Alarm [ K9 ]"', f"tag fallback quoting (system={system})")
        eq(r2["name_in_db"], "", "no member -> no name_in_db")


class _NoCe:
    """A stub system with the C&E capability OFF - the plugin-seam gate test (no type-id branching)."""
    class capabilities:
        needs_ce_matrix = False
        needs_diagnosis_blocks = False


def test_stage_capability_gate_skips_ce():
    """stage(system=no-C&E) must stop after 310: C&E columns absent, database still saved."""
    import os
    import tempfile
    from pipeline5 import config
    from pipeline5.phases.staging import iolist as staging
    with tempfile.TemporaryDirectory() as tmp:
        orig = config.paths._BUILTIN_DATABASE if hasattr(config, "paths") else None
        from pipeline5.config import paths as cfg_paths
        saved = cfg_paths._BUILTIN_DATABASE
        cfg_paths._BUILTIN_DATABASE = tmp
        try:
            database, findings = staging.stage(system=_NoCe())
            row = next(iter(database["signals"]), None)
            ok(row is not None, "signals staged")
            eq(str(row.get("matrix_areas") or ""), "", "no C&E enrichment ran")
            eq(row.get("combined_FLD"), row.get("iol_FLD"), "combined_FLD == iol_FLD without C&E")
            ok(os.path.exists(os.path.join(tmp, "signals.csv")), "the 310-only staging still SAVED")
            eq(len(list(database["diagnosis_cabinets"])), 0, "DiagnosisBlocks skipped (capability off)")
        finally:
            cfg_paths._BUILTIN_DATABASE = saved


def test_engine_raises_on_undeclared_emitter_kind():
    """Coupling #2's guarantee, asserted at the GUARD (refuter round 2: a bare raises(KeyError,...)
    passed incidentally via SCL_RENDERERS[name] - so the assertion pins the guard's own message):
    a system that fails to declare a READY emit kind gets the engine's raise, never a silent
    default writer; an UNKNOWN kind additionally must not fall through to the CreationInfo CSV."""
    import os
    import tempfile
    from pipeline5.truth.database import Database
    from pipeline5.phases.software_blocks import build_engine as engine
    from pipeline5.phases.software_blocks import builder_registry as registry

    @registry.builds("99_Refuter Block", emit="scl")            # a READY kind, declared for this test
    def _refuter_block(_db):  # noqa: ANN001
        return None

    @registry.builds("98_Mystery Block", emit="mystery")        # an UNKNOWN kind - the fallthrough path
    def _mystery_block(_db):  # noqa: ANN001
        return None

    class _EmitterlessSystem:
        id = "stub_without_emitters"
        emitters: dict = {}

    def _one_block_db(name):
        blocks, members = engine.software_blocks_table(), engine.software_block_members_table()
        blocks.add(name=name, template_ref="", columns=["TemplateType"], keys=["TemplateType"])
        return Database([blocks, members])

    for name in ("99_Refuter Block", "98_Mystery Block"):
        with tempfile.TemporaryDirectory() as tmp:
            try:
                engine.project(_one_block_db(name), out_dir=tmp, import_dir=tmp,
                               system=_EmitterlessSystem())
                ok(False, f"{name}: an undeclared kind must raise")
            except KeyError as e:
                ok("declares no emitter" in str(e),
                   f"{name}: the ENGINE GUARD must raise (not an incidental KeyError): {e}")
            ok(not [f for f in os.listdir(tmp) if f.endswith(".csv")],
               f"{name}: nothing may be silently written as a CreationInfo CSV")


if __name__ == "__main__":
    import sys
    sys.exit(run("system_siemens", [
        ("descriptor_shape", test_descriptor_shape),
        ("tia_symbols_round_trip", test_tia_symbols_round_trip),
        ("emitters_declare_ready_kinds", test_emitters_declare_ready_kinds),
        ("builders_proxy_reflects_module_registry", test_builders_proxy_reflects_module_registry),
        ("write_back_binding_parity_with_and_without_system", test_write_back_binding_parity_with_and_without_system),
        ("stage_capability_gate_skips_ce", test_stage_capability_gate_skips_ce),
        ("engine_raises_on_undeclared_emitter_kind", test_engine_raises_on_undeclared_emitter_kind),
    ]))
