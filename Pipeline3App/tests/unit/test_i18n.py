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


if __name__ == "__main__":
    raise SystemExit(run("i18n", [
        ("known_key", test_known_key),
        ("unknown_key_falls_back", test_unknown_key_falls_back),
        ("missing_lang_falls_back_to_en", test_missing_lang_falls_back_to_en),
        ("format", test_format),
        ("all_phase_headers_present", test_all_phase_headers_present),
        ("renamed_diag_swblocks", test_renamed_diag_swblocks),
    ]))
