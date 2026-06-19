"""M1 gate: the i18n table + tr()."""
from _harness import run, eq, ok
from pipeline3.core import i18n


def test_known_key():
    eq(i18n.tr("ph_validation", "en"), "Documents Validation")
    eq(i18n.tr("ph_validation", "it"), "Validazione Documenti")


def test_unknown_key_falls_back():
    eq(i18n.tr("does_not_exist", "en"), "does_not_exist")


def test_missing_lang_falls_back_to_en():
    eq(i18n.tr("ph_reporting", "de"), i18n.tr("ph_reporting", "en"))


def test_format():
    # tr never crashes on stray fmt; with no placeholder it returns the text unchanged
    eq(i18n.tr("ph_staging", "en", x=1), "Documents Staging")


def test_all_phase_headers_present():
    for k in ("ph_validation", "ph_fill", "ph_staging", "ph_interfaces", "ph_signals",
              "ph_diagnosis", "ph_hardware", "ph_software", "ph_reporting", "pb_run_pipeline"):
        for lang in ("en", "it"):
            ok(i18n.tr(k, lang) != k, f"{k}/{lang} missing")


def test_renamed_diag_swblocks():
    eq(i18n.tr("pb_gen_diag_swblocks", "en"), "Generate Diag Software Blocks")


def test_validation_keys_have_both_langs():
    vkeys = [k for k in i18n.STRINGS if k.startswith("v_")]
    ok(len(vkeys) >= 40, f"expected the full v_* validation set, found {len(vkeys)}")
    for k in vkeys:
        for lang in ("en", "it"):
            ok(i18n.STRINGS[k].get(lang), f"{k}/{lang} missing")


def test_validation_it_differs_from_en():
    eq(i18n.tr("v_addr_format", "en"), "Invalid address format")
    ok(i18n.tr("v_addr_format", "it") != i18n.tr("v_addr_format", "en"), "IT must differ from EN")


def test_validation_format_placeholders():
    eq(i18n.tr("v_too_many_nodes", "en", n=200), "Too many nodes: 200 (max 126)")
    ok("{addr}" not in i18n.tr("v_matrix_addr_kind", "en", addr="Q0.0"))


if __name__ == "__main__":
    raise SystemExit(run("i18n", [
        ("known_key", test_known_key),
        ("unknown_key_falls_back", test_unknown_key_falls_back),
        ("missing_lang_falls_back_to_en", test_missing_lang_falls_back_to_en),
        ("format", test_format),
        ("all_phase_headers_present", test_all_phase_headers_present),
        ("renamed_diag_swblocks", test_renamed_diag_swblocks),
        ("validation_keys_have_both_langs", test_validation_keys_have_both_langs),
        ("validation_it_differs_from_en", test_validation_it_differs_from_en),
        ("validation_format_placeholders", test_validation_format_placeholders),
    ]))
