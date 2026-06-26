"""Sheet-name resolution (core.config.js_to_re / resolve_sheets / resolve_sheet)."""
from _harness import run, eq, ok
from pipeline4.core import config

_AVAILABLE = ["NET SAFETY 50", "NET SAFETY 51", "CAUSE&EFFECT MATRIX", "AREA 1", "DiagnosisBlocks"]


def test_js_to_re_strips_flags():
    eq(config.js_to_re("/NET SAFETY \\d+/i"), "NET SAFETY \\d+", "trailing /flags stripped")
    eq(config.js_to_re("/NET SAFETY \\d+/"), "NET SAFETY \\d+", "bare /pattern/ unwrapped")
    eq(config.js_to_re("CAUSE&EFFECT"), "CAUSE&EFFECT", "a plain pattern is unchanged")


def test_resolve_sheets_regex_and_order():
    eq(config.resolve_sheets("/NET SAFETY \\d+/", _AVAILABLE), ["NET SAFETY 50", "NET SAFETY 51"],
       "regex matches both NET SAFETY sheets, in workbook order")
    eq(config.resolve_sheet("/CAUSE.?EFFECT/", _AVAILABLE), "CAUSE&EFFECT MATRIX", "first match")
    eq(config.resolve_sheet("/nope/", _AVAILABLE), None, "no match -> None")


def test_resolve_is_case_insensitive_and_deduped():
    eq(config.resolve_sheets("net safety 50", _AVAILABLE), ["NET SAFETY 50"], "case-insensitive")
    eq(config.resolve_sheets(["/NET SAFETY/", "/SAFETY 5/"], _AVAILABLE),
       ["NET SAFETY 50", "NET SAFETY 51"], "two patterns, each name appears once")


def test_invalid_regex_falls_back_to_literal():
    # an invalid regex ('AREA [1') must not crash - it falls back to an exact case-insensitive match
    eq(config.resolve_sheets("AREA [1", _AVAILABLE), [], "invalid regex, no literal match")
    eq(config.resolve_sheets("area 1", _AVAILABLE), ["AREA 1"], "literal fallback still matches by name")


if __name__ == "__main__":
    import sys
    sys.exit(run("sheets", [
        ("js_to_re_strips_flags", test_js_to_re_strips_flags),
        ("resolve_sheets_regex_and_order", test_resolve_sheets_regex_and_order),
        ("resolve_is_case_insensitive_and_deduped", test_resolve_is_case_insensitive_and_deduped),
        ("invalid_regex_falls_back_to_literal", test_invalid_regex_falls_back_to_literal),
    ]))
