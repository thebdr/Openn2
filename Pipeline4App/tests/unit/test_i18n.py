"""core/i18n.py - the EN/IT string table for the GUI chrome. Pure + data-independent."""
from _harness import run, eq, ok
from pipeline4.core import i18n


def test_tr_basics():
    eq(i18n.tr("pb_run_pipeline", "en"), "Run Pipeline")
    eq(i18n.tr("pb_run_pipeline", "it"), "Esegui Pipeline")
    eq(i18n.tr("pb_run_pipeline"), "Run Pipeline", "default lang is en")


def test_tr_unknown_key_falls_back_to_key():
    eq(i18n.tr("does_not_exist", "it"), "does_not_exist", "an unknown key returns itself (visible miss)")


def test_tr_format_and_safe_format():
    eq(i18n.tr("st_language", "en", code="it"), "language: it")
    eq(i18n.tr("st_language", "it", code="en"), "lingua: en")
    # a missing placeholder must not crash - the raw template is returned
    eq(i18n.tr("st_language", "en"), "language: {code}", "missing fmt key -> raw template, no crash")


def test_normalize():
    eq(i18n.normalize("IT"), "it")
    eq(i18n.normalize("en"), "en")
    eq(i18n.normalize("fr"), "en", "unsupported -> default en")
    eq(i18n.normalize(None), "en")
    eq(i18n.normalize("  It "), "it", "trimmed + lowercased")


def test_every_entry_has_both_languages():
    for key, entry in i18n.STRINGS.items():
        ok(entry.get("en"), f"{key} has EN")
        ok(entry.get("it"), f"{key} has IT")


if __name__ == "__main__":
    import sys
    sys.exit(run("i18n", [
        ("tr_basics", test_tr_basics),
        ("tr_unknown_key_falls_back_to_key", test_tr_unknown_key_falls_back_to_key),
        ("tr_format_and_safe_format", test_tr_format_and_safe_format),
        ("normalize", test_normalize),
        ("every_entry_has_both_languages", test_every_entry_has_both_languages),
    ]))
