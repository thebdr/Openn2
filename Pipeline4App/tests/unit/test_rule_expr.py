"""The reusable rule-expression engine (core/rule_expr): predicate `test` + template `render`."""
from _harness import run, eq, ok
from pipeline4.core import rule_expr as rx


def test_regex_and_equality():
    ctx = {"desc": "EMERGENCY PUSH-BUTTON PRESSED", "type_hw": "DI", "addr": "I0.0"}
    ok(rx.test("desc ~ /EMERGENCY PUSH.BUTTON PRES/", ctx), "ci regex search with . wildcard")
    eq(rx.test("desc ~ /fire alarm/", ctx), False, "no match -> False")
    ok(rx.test('type_hw = "DI"', ctx), "string equality")
    ok(rx.test('type_hw != "XX"', ctx), "string inequality")
    ok(rx.test("addr ~ /i/", ctx), "case-insensitive single letter (the In gate)")


def test_numeric_and_funcs():
    ok(rx.test("id_node > 0", {"id_node": "3"}), "numeric > with coercion")
    eq(rx.test("id_node > 0", {"id_node": ""}), False, "non-numeric -> comparison False")
    ok(rx.test("len(desc) > 3", {"desc": "ABCD"}), "len() > N")
    eq(rx.test("len(desc) > 3", {"desc": "AB"}), False, "len() short")
    ok(rx.test("numeric(x)", {"x": "12"}), "numeric() true")
    eq(rx.test("numeric(x)", {"x": "ab"}), False, "numeric() false")
    ok(rx.test("present(type_hw)", {"type_hw": "DI"}), "present() true")
    ok(rx.test("blank(type_hw)", {"type_hw": "   "}), "blank() true on whitespace")
    ok(rx.test("isdigit(extract(d2,/AREA ./,last))", {"d2": "EMERG RESET AREA 3"}), "isdigit(extract last)")
    eq(rx.test("isdigit(extract(d2,/AREA ./,last))", {"d2": "EMERG RESET AREA *"}), False, "non-digit area")


def test_boolean_composition():
    ctx = {"desc": "DOOR OPEN CH 1", "d2": "CH 1"}
    ok(rx.test("desc ~ /DOOR.*OPEN/ and d2 ~ /CH/", ctx), "and")
    ok(rx.test("desc ~ /nope/ or d2 ~ /CH/", ctx), "or")
    ok(rx.test("not desc ~ /nope/", ctx), "not")
    ok(rx.test("(desc ~ /DOOR/ or desc ~ /x/) and d2 ~ /CH/", ctx), "parens")


def test_in_list():
    ok(rx.test('script_type in ["KQ","KI"]', {"script_type": "KI"}), "in list membership")
    eq(rx.test('script_type in ["KQ","KI"]', {"script_type": "DD"}), False, "not in list")


def test_extract_parts():
    eq(rx.render("E{extract(d2,/CH./,last)}/2", {"d2": "FOO CH7 BAR"}), "E7/2", "last char of first CH. match")
    eq(rx.render("N{extract(d2,/CELL.\\d/,last)}/2", {"d2": "ENCODER CELL 4"}), "N4/2", "CELL.<digit> last char")
    eq(rx.render("{extract(d2,/A(.)C/,group1)}", {"d2": "xAyCz"}), "y", "group<N> capture")
    eq(rx.render("X{extract(d2,/NOPE/,last)}", {"d2": "xAyCz"}), "X", "no match -> empty extraction")


def test_render_tokens():
    ctx = {"type_hw": "PLC", "INPUT_REQUIRED": "<input required>"}
    eq(rx.render("{type_hw}", ctx), "PLC", "field token")
    eq(rx.render("{INPUT_REQUIRED}", ctx), "<input required>", "caller-supplied sentinel field")
    eq(rx.render("KQ", ctx), "KQ", "literal, no holes")
    eq(rx.render("R{extract(d2,/AREA ./,last)}", {"d2": "AREA 5"}), "R5", "prefix + extract")


def test_empty_predicate_is_true():
    ok(rx.test("", {}), "empty when -> always matches")
    ok(rx.test("   ", {}), "blank when -> always matches")


def test_errors():
    for bad in ("desc ~ notaregex", "len(", "foo(x)", "desc = ", "extract(d2,/re/)"):
        try:
            rx.test(bad, {"desc": "x", "d2": "y"})
            ok(False, f"{bad!r} should raise")
        except rx.RuleError:
            ok(True, f"{bad!r} raised RuleError")


if __name__ == "__main__":
    import sys
    sys.exit(run("rule_expr", [
        ("regex_and_equality", test_regex_and_equality),
        ("numeric_and_funcs", test_numeric_and_funcs),
        ("boolean_composition", test_boolean_composition),
        ("in_list", test_in_list),
        ("extract_parts", test_extract_parts),
        ("render_tokens", test_render_tokens),
        ("empty_predicate_is_true", test_empty_predicate_is_true),
        ("errors", test_errors),
    ]))
