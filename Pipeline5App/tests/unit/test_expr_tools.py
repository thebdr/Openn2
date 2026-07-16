"""The expr editor tooling (core/expr/tools.py - UI_REFRESH_PLAN G1): position tokens, the
compile-only lint (expressions + render templates), and the autocomplete word lists."""
from _harness import run, eq, ok
from pipeline5.language import expr


def _kinds(text):
    return [(kind, text[s:e]) for kind, s, e in expr.tokens(text)]


def test_tokens_positions_and_kinds():
    text = '$f ~ /CH\\d/ and len("x") > 3'
    got = _kinds(text)
    eq(got[0], ("field", "$f"), "a $field token")
    eq(got[1], ("op", "~"), "the regex operator")
    eq(got[2], ("regex", "/CH\\d/"), "the regex literal")
    eq(got[3], ("keyword", "and"), "keywords classified")
    eq(got[4], ("func", "len"), "host functions classified")
    ok(("string", '"x"') in got, "the string literal")
    ok(("number", "3") in got, "the number literal")
    got2 = _kinds("count(signals)")
    eq(got2[0], ("data_func", "count"), "data functions classified")
    eq(got2[2], ("ident", "signals"), "a bare table word stays ident")


def test_tokens_lenient_on_bad_chars():
    got = expr.tokens("$f ? 3")
    kinds = [k for k, _s, _e in got]
    eq(kinds, ["field", "error", "number"], "the bad char is one error token, the scan resumes")


def test_check_unknown_field_precise_span():
    scope = expr.Scope(("name", "bit"))
    issues = expr.check("$name = $typo", scope)
    eq(len(issues), 1, "one issue")
    i = issues[0]
    eq(("$typo", i.message), ("$name = $typo"[i.start:i.end], "unknown field $typo"),
       "the span covers exactly the bad field token")
    eq(expr.check("$name = $bit", scope), [], "known fields are clean")
    eq(expr.check("", scope), [], "blank = the always-true predicate, clean")


def test_check_syntax_error_and_bad_char():
    issues = expr.check("$f and", None)
    eq(len(issues), 1, "a syntax error is one issue")
    ok(issues[0].start == 0 and issues[0].end == len("$f and"), "whole-text span for syntax")
    issues2 = expr.check("$f ? 1", None)
    ok(any(i.message == "unexpected character" for i in issues2), "bad char reported")


def test_check_template_holes_with_spec():
    scope = expr.Scope(("n", "name"))
    eq(expr.check_template("plain text, no holes - never an error {}", scope), [],
       "verbatim text + empty holes are clean")
    eq(expr.check_template("{$n:03d} and {$name}", scope), [], "a :spec is not mistaken for syntax")
    issues = expr.check_template("x {$typo} y", scope)
    eq(len(issues), 1)
    tpl = "x {$typo} y"
    eq(tpl[issues[0].start:issues[0].end], "$typo", "the span lands inside the template")


def test_word_lists():
    names = expr.function_names()
    for fn in ("clean", "extract", "let", "where", "lookup", "count"):
        ok(fn in names, f"{fn} in the autocomplete list")


if __name__ == "__main__":
    import sys
    sys.exit(run("expr_tools", [
        ("tokens_positions_and_kinds", test_tokens_positions_and_kinds),
        ("tokens_lenient_on_bad_chars", test_tokens_lenient_on_bad_chars),
        ("check_unknown_field_precise_span", test_check_unknown_field_precise_span),
        ("check_syntax_error_and_bad_char", test_check_syntax_error_and_bad_char),
        ("check_template_holes_with_spec", test_check_template_holes_with_spec),
        ("word_lists", test_word_lists),
    ]))
