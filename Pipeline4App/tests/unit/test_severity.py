"""The severity taxonomy (core.severity) + the GUI log-level display filter (config.load_app_ui reading
app_config.yaml). First-char level resolution; the shown-set; the DEBUG addition."""
from _harness import run, eq, ok
from pipeline4.core import config, severity


def test_levels_set():
    eq(severity.LEVELS, ("FAIL", "ERROR", "WARN", "INFO", "SKIP", "PASS", "DEBUG"), "the 7 finding levels")
    ok("DEBUG" in severity.LEVELS, "DEBUG was added")
    ok("FAIL" in severity.HALTING and "ERROR" not in severity.HALTING, "FAIL halts; ERROR does not")
    eq(severity.BANNER, "PHASE", "PHASE is the banner, not a finding level")
    # every finding level has a distinct first char (so first-char parsing is unambiguous)
    eq(len({lvl[0] for lvl in severity.LEVELS}), len(severity.LEVELS), "distinct first chars F E W I S P D")


def test_resolve_first_char_or_full():
    eq(severity.resolve("F"), "FAIL")
    eq(severity.resolve("FAIL"), "FAIL", "a full name resolves by its first char")
    eq(severity.resolve("fail"), "FAIL", "case-insensitive")
    eq(severity.resolve("D"), "DEBUG")
    eq(severity.resolve("Info…"), "INFO", "first char wins")
    ok(severity.resolve("X") is None and severity.resolve("") is None, "unknown / blank -> None")


def test_resolve_set_includes_banner():
    s = severity.resolve_set(["F", "E", "W", "S", "P", "D"])
    eq(s, {"PHASE", "FAIL", "ERROR", "WARN", "SKIP", "PASS", "DEBUG"}, "the list + the always-on PHASE banner")
    ok("INFO" not in s, "INFO omitted from this list -> hidden")
    eq(severity.resolve_set(["WARN", "FAIL"]), {"PHASE", "WARN", "FAIL"}, "full names work too")


def test_default_shown_hides_debug():
    d = severity.default_shown()
    ok("DEBUG" not in d, "DEBUG hidden by default (no config)")
    for lvl in ("FAIL", "ERROR", "WARN", "INFO", "SKIP", "PASS", "PHASE"):
        ok(lvl in d, f"{lvl} shown by default")


def test_load_app_ui_reads_app_config():
    # the builtin config_project/app_config.yaml ships log_levels: [F, E, W, I, S, P, D] (all 7)
    ui = config.load_app_ui()
    levels = ui["log_levels"]
    eq(levels, {"PHASE"} | set(severity.LEVELS), "all 7 finding levels + the PHASE banner")


if __name__ == "__main__":
    import sys
    sys.exit(run("severity", [
        ("levels_set", test_levels_set),
        ("resolve_first_char_or_full", test_resolve_first_char_or_full),
        ("resolve_set_includes_banner", test_resolve_set_includes_banner),
        ("default_shown_hides_debug", test_default_shown_hides_debug),
        ("load_app_ui_reads_app_config", test_load_app_ui_reads_app_config),
    ]))
