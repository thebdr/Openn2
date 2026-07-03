"""The severity taxonomy (core.severity) + the GUI log-level display filter (config.load_app_ui reading
app_config.yaml). First-char level resolution; the shown-set; the DEBG rename (4-letter codes)."""
from _harness import run, eq, ok
from pipeline4.core import config, severity


def test_levels_set():
    eq(severity.LEVELS, ("FAIL", "ERRR", "WARN", "INFO", "SKIP", "PASS", "RSLT", "DEBG"), "the 8 log levels (RSLT = the phase-result line)")
    ok("DEBG" in severity.LEVELS, "DEBG was added")
    ok("FAIL" in severity.HALTING and "ERRR" not in severity.HALTING, "FAIL halts; ERRR does not")
    eq(severity.BANNER, "PHASE", "PHASE is the banner, not a finding level")
    # every finding level has a distinct first char (so first-char parsing is unambiguous)
    eq(len({lvl[0] for lvl in severity.LEVELS}), len(severity.LEVELS), "distinct first chars F E W I S P R D")


def test_resolve_first_char_or_full():
    eq(severity.resolve("F"), "FAIL")
    eq(severity.resolve("FAIL"), "FAIL", "a full name resolves by its first char")
    eq(severity.resolve("fail"), "FAIL", "case-insensitive")
    eq(severity.resolve("D"), "DEBG")
    eq(severity.resolve("ERROR"), "ERRR", "a legacy full name resolves by first char")
    eq(severity.resolve("Info…"), "INFO", "first char wins")
    ok(severity.resolve("X") is None and severity.resolve("") is None, "unknown / blank -> None")


def test_resolve_set_includes_banner():
    s = severity.resolve_set(["F", "E", "W", "S", "P", "D"])
    eq(s, {"PHASE", "FAIL", "ERRR", "WARN", "SKIP", "PASS", "DEBG"}, "the list + the always-on PHASE banner")
    ok("INFO" not in s, "INFO omitted from this list -> hidden")
    eq(severity.resolve_set(["WARN", "FAIL"]), {"PHASE", "WARN", "FAIL"}, "full names work too")


def test_default_shown_hides_debug():
    d = severity.default_shown()
    ok("DEBG" not in d, "DEBG hidden by default (no config)")
    for lvl in ("FAIL", "ERRR", "WARN", "INFO", "SKIP", "PASS", "RSLT", "PHASE"):
        ok(lvl in d, f"{lvl} shown by default")


def test_load_app_ui_reads_app_config():
    # the builtin app_config.yaml is the LIVE store of the user's Levels choice (app-scoped prefs) -
    # assert the CONTRACT, never the current value: a valid subset of the levels, with the
    # unhideable PHASE banner + FAIL + ERRR always present.
    ui = config.load_app_ui()
    levels = ui["log_levels"]
    ok(levels <= {"PHASE"} | set(severity.LEVELS), "only known levels")
    ok({"PHASE", "FAIL", "ERRR"} <= levels, "the banner + the failures are always shown")


if __name__ == "__main__":
    import sys
    sys.exit(run("severity", [
        ("levels_set", test_levels_set),
        ("resolve_first_char_or_full", test_resolve_first_char_or_full),
        ("resolve_set_includes_banner", test_resolve_set_includes_banner),
        ("default_shown_hides_debug", test_default_shown_hides_debug),
        ("load_app_ui_reads_app_config", test_load_app_ui_reads_app_config),
    ]))
