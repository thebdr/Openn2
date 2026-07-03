"""STEP 1 i18n - the LOGS: the validation finding messages are bilingual and a finding's detail is built
in the ACTIVE language (the whole reason i18n exists - an IT operator reads IT findings). EN stays verbatim
(parity), IT comes from PL3. Pure + data-independent."""
from _harness import run, eq, ok
from pipeline4.domain.validation import messages
from pipeline4.domain.validation.model import entry


def test_messages_bilingual():
    eq(len(messages.MESSAGES), 56, "all 56 phase-100 slugs present (+ the 6 step-4 diagnosis slugs)")
    for slug, e in messages.MESSAGES.items():
        ok(e.get("en"), f"{slug} has EN")
        ok(e.get("it"), f"{slug} has IT")


def test_en_unchanged_parity():
    # EN text is byte-identical to the verbatim PL3/prior text (the finding-detail parity oracle).
    eq(messages.msg("row_ok"), "All checks passed")
    eq(messages.msg("addr_format"), "Invalid address format")
    eq(messages.msg("ip_duplicated", ip="1.2.3.4", first="A1"), "Duplicated IP 1.2.3.4 (first seen at A1)")


def test_active_lang_switches_and_restores():
    eq(messages.current_lang(), "en", "default ambient is en")
    eq(messages.msg("row_ok"), "All checks passed")
    with messages.active_lang("it"):
        eq(messages.current_lang(), "it")
        eq(messages.msg("row_ok"), "Tutti i controlli superati")
        eq(messages.msg("ip_duplicated", ip="1.2.3.4", first="A1"),
           "IP duplicato 1.2.3.4 (prima occorrenza in A1)")
    eq(messages.current_lang(), "en", "the ambient is restored after the block")
    eq(messages.msg("row_ok"), "All checks passed")


def test_active_lang_nested_restore():
    with messages.active_lang("it"):
        with messages.active_lang("en"):
            eq(messages.msg("row_ok"), "All checks passed")
        eq(messages.msg("row_ok"), "Tutti i controlli superati", "the inner block restores to it")
    eq(messages.current_lang(), "en")


def test_entry_builds_localized_detail():
    f_en = entry("FAIL", 110, "addr_format", location="S!A1")
    eq(f_en.detail, "Invalid address format", "default-language finding is EN")
    with messages.active_lang("it"):
        f_it = entry("FAIL", 110, "addr_format", location="S!A1")
    eq(f_it.detail, "Formato indirizzo non valido", "the finding detail is built in the active language")
    # PL3-faithful: the uid hashes the localized detail, so treatments key per operating language
    ok(f_en.uid != f_it.uid, "EN vs IT findings have distinct uids (detail localized -> uid follows)")


def test_bad_or_missing_fmt_never_crashes():
    eq(messages.msg("ip_duplicated"), "Duplicated IP {ip} (first seen at {first})", "missing fmt -> raw template")
    eq(messages.msg("no_such_slug"), "<no_such_slug>", "unknown slug -> loud marker")


def test_always_plural_no_hedge():
    # COSMETIC RULE: never the singular-or-plural hedge ("(s)" in EN, a word-final "/i"|"/e" in IT, e.g.
    # foglio/i) - always plural. (A "/" between two words like "Output/internal" is NOT a hedge.)
    import re
    hedge_it = re.compile(r"[a-zà-ù]/[ie]\b")
    for slug, e in messages.MESSAGES.items():
        for lang in ("en", "it"):
            text = e[lang]
            ok("(s)" not in text, f"{slug}/{lang} has no '(s)' hedge: {text!r}")
            ok(not hedge_it.search(text), f"{slug}/{lang} has no word-final '/i'|'/e' hedge: {text!r}")
    # the count-bearing summaries read plural even at 1
    eq(messages.msg("iolist_summary", sheets=1, nodes=1), "1 sheets processed, 1 nodes")
    with messages.active_lang("it"):
        eq(messages.msg("iolist_summary", sheets=1, nodes=1), "1 fogli elaborati, 1 nodi")


if __name__ == "__main__":
    import sys
    sys.exit(run("validation_i18n", [
        ("messages_bilingual", test_messages_bilingual),
        ("en_unchanged_parity", test_en_unchanged_parity),
        ("active_lang_switches_and_restores", test_active_lang_switches_and_restores),
        ("active_lang_nested_restore", test_active_lang_nested_restore),
        ("entry_builds_localized_detail", test_entry_builds_localized_detail),
        ("bad_or_missing_fmt_never_crashes", test_bad_or_missing_fmt_never_crashes),
        ("always_plural_no_hedge", test_always_plural_no_hedge),
    ]))
