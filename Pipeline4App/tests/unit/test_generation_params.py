"""The relocated generation constants (UI_REFRESH_PLAN F): config.load_generation_params (active ->
builtin fallback, raise when neither), the diagnosis knobs' strictness, and the @builds emit-kind
declaration that replaced the hardcoded FC-XML name-set."""
from _harness import run, eq, ok
from pipeline4.core import config
from pipeline4.domain import diagnosis, diagnosis_scl
from pipeline4.domain.blocks import registry


def test_builtin_generation_params_load():
    params = config.load_generation_params()
    diag = params.get("diagnosis") or {}
    eq(diag.get("alarm_dwords"), ["ALARM1", "ALARM2"], "the shipped alarm DWord names")
    eq(diag.get("warning_dwords"), ["WARNING1", "WARNING2"], "the shipped warning DWord names")
    eq(diag.get("default_scl_variant"), 1, "the shipped default variant")
    eq(diag.get("cabinet_instance_template"), "S1.CABINET{$index}.{$role}",
       "the instance template (core/expr holes)")
    eq(diag.get("plc_binding_placeholder"), "$PLC_Binding$", "the DiagList sentinel")


def test_diag_params_and_instance_render():
    p = diagnosis_scl._diag_params()
    eq(p["alarm_dwords"], ["ALARM1", "ALARM2"], "loader -> typed knobs")
    eq(p["default_variant"], 1)
    inst = diagnosis_scl._inst("001", "ALARM1", p["instance_template"])
    eq(inst, "S1.CABINET001.ALARM1", "the configured template renders through core/expr")
    eq(diagnosis._binding_sentinel(), "$PLC_Binding$", "the sentinel reads from the params")


def test_missing_file_raises():
    import os
    orig_active, orig_builtin = config.generation_params_file, config.builtin_config_project_dir
    config.generation_params_file = lambda: os.path.join("Z:\\", "no_such", "generation_params.yaml")
    config.builtin_config_project_dir = lambda: os.path.join("Z:\\", "no_such_builtin")
    try:
        try:
            config.load_generation_params()
            ok(False, "a missing file (both candidates) must raise")
        except RuntimeError as error:
            ok("generation_params.yaml missing" in str(error), "the error names the file")
    finally:
        config.generation_params_file, config.builtin_config_project_dir = orig_active, orig_builtin


def test_emit_kind_declaration():
    import pipeline4.domain.blocks.builders  # noqa: F401  (importing registers the builders)
    eq(registry.emit_kind("03_Zone Cumulative"), "fc_xml", "03 declares the FC-XML surface")
    eq(registry.emit_kind("06_Feedback Error"), "csv", "an undeclared builder defaults to csv")
    eq(registry.emit_kind("no such block"), "csv", "unregistered names default to csv")


if __name__ == "__main__":
    import sys
    sys.exit(run("generation_params", [
        ("builtin_generation_params_load", test_builtin_generation_params_load),
        ("diag_params_and_instance_render", test_diag_params_and_instance_render),
        ("missing_file_raises", test_missing_file_raises),
        ("emit_kind_declaration", test_emit_kind_declaration),
    ]))
