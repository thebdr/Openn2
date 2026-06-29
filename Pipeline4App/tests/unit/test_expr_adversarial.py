r"""ADVERSARIAL edge-case tests for core/expr — parity vs rule_expr + correctness.

Probes the parity-critical + tricky areas the implementer flagged:
  * extract capture-first vs whole-match slice; the -1:==last / :1==first equivalence across
    /CH./ /CELL.\d/ /AREA ./ and edge strings (empty match, match-at-end, multi-char);
  * IGNORECASE at BOTH ~ and extract;
  * let scoping (shadow / out-of-scope binding / nested / bind-once);
  * $field scope validation vs dotted silent-empty;
  * render: format-spec coercion, the three missing-key modes, empty hole, literal braces, located bad-spec;
  * coalesce/if truthiness edge values (0 / "" / "0" / 0.0);
  * data funcs: where-pred over a row column; node_of boundary (==start, ==end, just-outside, % addr).
"""
from _harness import run, eq, ok, raises
from pipeline4.core import expr
from pipeline4.core import rule_expr as rx
from pipeline4.core.expr import Scope, ExprError


# =================================================================================================
# extract: -1: == rule_expr `last`, :1 == `first`, across patterns + edge strings (NO capture group)
# =================================================================================================
def test_extract_last_parity_matrix():
    pats = ["CH.", r"CELL.\d", "AREA ."]
    strings = [
        "FOO CH7 BAR", "ENCODER CELL 4", "EMERG RESET AREA 3",
        "xCHq", "CHz", "no match here", "ends with CH9", "AREA Q",
        "CELL 0 CELL 9",  # multiple matches -> search takes the FIRST
        "",
    ]
    for pat in pats:
        for sv in strings:
            ctx = {"d2": sv}
            rx_last = rx.render("{extract(d2,/%s/,last)}" % pat, ctx)
            ex_last = expr.evaluate("extract($d2, /%s/, -1:)" % pat, ctx)
            eq(ex_last, rx_last, "-1: == last  /%s/ on %r" % (pat, sv))
            rx_first = rx.render("{extract(d2,/%s/,first)}" % pat, ctx)
            ex_first = expr.evaluate("extract($d2, /%s/, :1)" % pat, ctx)
            eq(ex_first, rx_first, ":1 == first /%s/ on %r" % (pat, sv))


def test_extract_match_at_string_end_and_single_char():
    # match exactly at the end of the string
    eq(expr.evaluate("extract($d, /CH./, -1:)", {"d": "abcCH9"}), "9", "match at end, last char")
    eq(expr.evaluate("extract($d, /CH./, -1:)", {"d": "abcCH9"}),
       rx.render("{extract(d,/CH./,last)}", {"d": "abcCH9"}), "parity at-end")
    # a single-char whole match: -1: and :1 are the same char
    eq(expr.evaluate("extract($d, /X/, -1:)", {"d": "aXb"}), "X", "single-char match last")
    eq(expr.evaluate("extract($d, /X/, :1)", {"d": "aXb"}), "X", "single-char match first")


def test_extract_multidigit_capture():
    eq(expr.evaluate(r"extract($f, /CH(\d+)/)", {"f": "CH123"}), "123", "multi-digit capture group(1)")
    eq(expr.evaluate(r"extract($f, /CH(\d+)/, -1:)", {"f": "CH123"}), "3", "slice -1: applies to capture")
    eq(expr.evaluate(r"extract($f, /CELL (\d+)/, 2)", {"f": "CELL 4567"}), "6", "index 2 of capture '4567'")
    # capture-first uses group(1) even with multiple groups
    eq(expr.evaluate(r"extract($f, /(\d)(\d)(\d)/)", {"f": "x789"}), "7", "group(1) only of 3 groups")


def test_extract_no_match_variants():
    eq(expr.evaluate("extract($f, /ZZZ/)", {"f": "abc"}), "", "no match, no slice -> ''")
    eq(expr.evaluate("extract($f, /ZZZ/, -1:)", {"f": "abc"}), "", "no match + slice -> ''")
    eq(expr.evaluate(r"extract($f, /ZZ(\d+)/)", {"f": "abc"}), "", "no match capture -> ''")
    # out-of-range index on a short match -> ''
    eq(expr.evaluate("extract($f, /X/, 5)", {"f": "aXb"}), "", "index past end of 1-char match -> ''")


def test_extract_ignorecase_both_sides():
    eq(expr.test("$d ~ /door/", {"d": "DOOR OPEN"}), True, "~ IGNORECASE")
    eq(expr.test("$d ~ /DOOR/", {"d": "door open"}), True, "~ IGNORECASE reverse")
    eq(expr.evaluate("extract($d, /door(.)/)", {"d": "DOORX"}), "X", "extract IGNORECASE capture")
    eq(expr.evaluate("extract($d, /ch./, -1:)", {"d": "FOO CH7"}), "7", "extract lower-pat on upper text")
    # parity: rule_expr extract is also IGNORECASE
    eq(expr.evaluate("extract($d, /ch./, -1:)", {"d": "FOO CH7"}),
       rx.render("{extract(d,/ch./,last)}", {"d": "FOO CH7"}), "extract IGNORECASE parity")


# =================================================================================================
# let scoping
# =================================================================================================
def test_let_shadow_and_bind_once():
    # bind-once: b binds from the ORIGINAL ctx x, then x is rebound; b must keep the original
    eq(expr.evaluate("let(b := $x, x := $y ; concat($b, $x))", {"x": "A", "y": "B"}), "AB", "bind-once order")
    # shadow: the bound x shadows ctx x in the body
    eq(expr.evaluate('let(x := concat($x, "!") ; $x)', {"x": "v"}), "v!", "shadow uses orig once")


def test_let_out_of_scope_binding_expr_rejected():
    # a binding expr referencing an unknown field (under strict scope) must raise at COMPILE
    raises(ExprError, lambda: expr.evaluate("let(a := $unknown ; $a)", {}, scope=Scope(["x"])))
    # a body referencing a NON-bound, NON-scope name must raise
    raises(ExprError, lambda: expr.evaluate("let(a := $x ; $b)", {"x": "1"}, scope=Scope(["x"])))


def test_let_earlier_binding_not_visible_to_prior():
    # 'a' is NOT yet bound when compiling 'b'... wait, b is AFTER a, so a IS visible. Test the reverse:
    # the FIRST binding cannot see a LATER one (forward ref) -> $b unknown under strict scope
    raises(ExprError, lambda: expr.evaluate("let(a := $b, b := $x ; $a)", {"x": "1"}, scope=Scope(["x"])))


def test_let_nested_inner_sees_outer():
    eq(expr.evaluate("let(a := $x ; let(b := concat($a, $a) ; concat($a, $b)))", {"x": "z"}), "zzz",
       "nested: inner body sees outer bind")
    # inner shadow of an outer let name
    eq(expr.evaluate('let(a := "1" ; let(a := "2" ; $a))', {}), "2", "inner let shadows outer let name")


def test_let_permissive_scope_admits_anything():
    eq(expr.evaluate("let(a := $whatever ; $a)", {}), "", "scope=None: unknown binding field -> ''")


# =================================================================================================
# $field scope validation vs dotted silent-empty
# =================================================================================================
def test_scope_unknown_top_vs_dotted_missing_subkey():
    sc = Scope(["obj"])
    # unknown TOP-LEVEL -> compile ExprError
    raises(ExprError, lambda: expr.evaluate("$nope", {}, scope=sc))
    # dotted missing SUB-key -> "" at eval, no throw (top is in scope)
    eq(expr.evaluate("$obj.missing", {"obj": {"a": "1"}}, scope=sc), "", "missing subkey silent-empty")
    # drilling a missing top under permissive -> ""
    eq(expr.evaluate("$x.y.z", {}), "", "missing top dotted permissive -> ''")
    # drilling into a non-dict scalar -> ''
    eq(expr.evaluate("$obj.a.b", {"obj": {"a": "scalar"}}, scope=sc), "", "drill into scalar -> ''")


# =================================================================================================
# render: format-spec coercion + missing modes + braces + located errors
# =================================================================================================
def test_render_format_spec_coercion():
    eq(expr.render("{$n:03d}", {"n": "0"}), "000", "'0' -> 000")
    eq(expr.render("{$n:03d}", {"n": 0}), "000", "int 0 -> 000")
    eq(expr.render("{$n:03d}", {"n": "5"}), "005", "'5' -> 005")
    eq(expr.render("{$n:03d}", {"n": "12"}), "012", "'12' -> 012")
    eq(expr.render("{$n:03d}", {"n": "7.9"}), "007", "int-conv truncates float-string via int(float())")
    eq(expr.render("{$f:.2f}", {"f": "1.5"}), "1.50", "float spec on string")
    eq(expr.render("{$f:.2f}", {"f": 1}), "1.00", "float spec on int")
    eq(expr.render("{$n:03d}", {"n": ""}), "", "blank stays blank")
    eq(expr.render("{$n:03d}", {"n": None}), "", "None stays blank")
    eq(expr.render("{$n:x}", {"n": "255"}), "ff", "hex conversion")
    eq(expr.render("{$n:b}", {"n": "5"}), "101", "binary conversion")


def test_render_bad_spec_located():
    # non-numeric under an int conversion -> located ExprError (carries the value)
    try:
        expr.render("{$n:03d}", {"n": "abc"})
        raise AssertionError("expected ExprError on non-numeric :d")
    except ExprError as e:
        ok("abc" in str(e) or "03d" in str(e), "bad-spec error is located/carries context")
    raises(ExprError, lambda: expr.render("{$f:.2f}", {"f": "notnum"}))


def test_render_missing_modes_precise():
    eq(expr.render("{$x}", {}, mode="empty"), "", "empty missing -> ''")
    eq(expr.render("{$x}", {}, mode="keep"), "{$x}", "keep missing -> literal token")
    eq(expr.render("{$x}", {"x": ""}, mode="keep"), "", "keep present-empty -> ''")
    eq(expr.render("{$x:03d}", {}, mode="keep"), "{$x:03d}", "keep keeps the WHOLE token incl spec")
    raises(ExprError, lambda: expr.render("{$x}", {}, mode="strict"))
    # keep on a dotted missing TOP -> literal
    eq(expr.render("{$obj.k}", {}, mode="keep"), "{$obj.k}", "keep dotted missing top -> literal")
    # keep on a dotted present top, missing subkey -> NOT a simple-missing top, so it EVALUATES -> ''
    eq(expr.render("{$obj.k}", {"obj": {}}, mode="keep"), "", "keep present-top dotted-missing -> '' (evaluates)")
    raises(ExprError, lambda: expr.render("{$x}", {}, mode="bogus"))


def test_render_non_simple_hole_modes():
    # a non-simple hole (a function call) is NOT subject to the simple-field missing check; it evaluates.
    # under keep, concat of a missing field still evaluates to '' (permissive engine), not the literal
    eq(expr.render("{concat($x, $y)}", {}, mode="keep"), "", "keep: non-simple hole evaluates")


def test_render_literal_braces_and_empty():
    eq(expr.render("{}", {}), "", "empty hole")
    eq(expr.render("{ }", {}), "", "blank hole")
    eq(expr.render("a{$x}b", {"x": "Z"}), "aZb", "interp + verbatim")
    eq(expr.render("no holes here", {}), "no holes here", "sentinel verbatim")
    eq(expr.render("<input required>", {}), "<input required>", "angle sentinel verbatim")


def test_render_spec_split_with_colon_in_extract_slice():
    # the spec splitter must NOT mistake the -1: slice colon for a format spec
    eq(expr.render("{extract($d,/CH./,-1:)}", {"d": "FOO CH7"}), "7", "slice colon not a spec")
    # a real spec AFTER an extract call
    eq(expr.render("{extract($d,/(\\d+)/):03d}", {"d": "x5"}), "005", "trailing :03d IS the spec")


# =================================================================================================
# coalesce / if truthiness edge values
# =================================================================================================
def test_coalesce_edge_values():
    eq(expr.evaluate('coalesce($a, "0")', {"a": ""}), "0", '"0" non-empty -> kept')
    eq(expr.evaluate("coalesce($a, $b)", {"a": "", "b": ""}), "", "all empty -> ''")
    # a numeric literal 0 -> s(0.0)=='0.0' non-empty -> returned as the float 0.0
    eq(expr.evaluate("coalesce($a, 0)", {"a": ""}), 0.0, "numeric 0 is non-empty (s='0.0') -> returned")
    eq(expr.evaluate("coalesce($a, $b)", {"a": "", "b": "x"}), "x", "first non-empty field")


def test_if_truthiness_edge():
    eq(expr.evaluate('if($c, "Y", "N")', {"c": "0"}), "Y", '"0" string is truthy')
    eq(expr.evaluate('if($c, "Y", "N")', {"c": ""}), "N", "empty falsy")
    eq(expr.evaluate('if($c, "Y", "N")', {"c": "   "}), "Y", "whitespace string is truthy (non-empty)")
    eq(expr.evaluate('if(0, "Y", "N")', {}), "N", "numeric 0 is falsy")
    eq(expr.evaluate('if(1, "Y", "N")', {}), "Y", "numeric 1 truthy")


# =================================================================================================
# data funcs: where-pred over a row column, count, node_of boundary
# =================================================================================================
def _db():
    return {"_db": {
        "signals": [
            {"name": "A", "type": "DI", "bit": "I0.0"},
            {"name": "B", "type": "DI", "bit": "I1.0"},
            {"name": "C", "type": "DO", "bit": "Q0.0"},
        ],
        "nodes": [
            {"node": "N1", "start_byte": "0", "end_byte": "7"},
            {"node": "N2", "start_byte": "8", "end_byte": "15"},
        ],
    }}


def test_where_pred_references_row_column():
    ctx = _db()
    rows = expr.evaluate('where(signals, $type = "DI" and $name != "A")', ctx)
    eq([r["name"] for r in rows], ["B"], "compound per-row predicate")
    # a $col not present in the row resolves to '' (permissive row scope)
    rows2 = expr.evaluate('where(signals, $nonexistent = "")', ctx)
    eq(len(rows2), 3, "missing row column -> '' -> all match = ''")
    # count with a predicate over a row column
    eq(expr.evaluate('count(signals, $type = "DI")', ctx), 2.0, "count filtered by row col")
    eq(expr.evaluate("count(signals)", ctx), 3.0, "count all")
    # an empty/missing table -> []
    eq(expr.evaluate("count(absent)", ctx), 0.0, "absent table -> 0")
    eq(expr.evaluate("where(absent)", ctx), [], "absent table where -> []")


def test_node_of_boundaries():
    ctx = _db()
    # exactly at start_byte of N1 (0) and end_byte of N1 (7) -> inclusive both ends
    eq(expr.evaluate('node_of("I0.0", nodes)', ctx)["node"], "N1", "byte == start_byte -> in")
    eq(expr.evaluate('node_of("I7.7", nodes)', ctx)["node"], "N1", "byte == end_byte -> in")
    eq(expr.evaluate('node_of("I8.0", nodes)', ctx)["node"], "N2", "byte == next start -> N2")
    eq(expr.evaluate('node_of("I15.0", nodes)', ctx)["node"], "N2", "byte == end of N2 -> N2")
    # just outside the whole range
    eq(expr.evaluate('node_of("I16.0", nodes)', ctx), {}, "byte just past end -> {}")
    eq(expr.evaluate('node_of("I99.0", nodes)', ctx), {}, "far out -> {}")
    # % prefixed addresses (PL4 uses %-prefixed bits)
    eq(expr.evaluate('node_of("%I12.3", nodes)', ctx)["node"], "N2", "%-prefixed addr parses")
    eq(expr.evaluate('node_of("%Q0.0", nodes)', ctx)["node"], "N1", "%Q addr -> byte 0 -> N1")
    # a non-addressable bit -> {}
    eq(expr.evaluate('node_of("", nodes)', ctx), {}, "empty bit -> {}")


def test_node_of_bad_byte_columns_skipped():
    ctx = {"_db": {"nodes": [
        {"node": "BAD", "start_byte": "x", "end_byte": "y"},
        {"node": "GOOD", "start_byte": "0", "end_byte": "100"},
    ]}}
    eq(expr.evaluate('node_of("I5.0", nodes)', ctx)["node"], "GOOD", "non-numeric range row skipped")


def test_lookup_and_unique_edges():
    ctx = _db()
    eq(expr.evaluate('lookup(signals, name, "B", bit)', ctx), "I1.0", "lookup hit")
    eq(expr.evaluate('lookup(signals, name, "ZZ", bit)', ctx), "", "lookup miss -> ''")
    eq(expr.evaluate("unique(type, signals)", ctx), ["DI", "DO"], "unique first-seen distinct")


if __name__ == "__main__":
    import sys
    sys.exit(run("expr_adversarial", [
        ("extract_last_parity_matrix", test_extract_last_parity_matrix),
        ("extract_match_at_string_end_and_single_char", test_extract_match_at_string_end_and_single_char),
        ("extract_multidigit_capture", test_extract_multidigit_capture),
        ("extract_no_match_variants", test_extract_no_match_variants),
        ("extract_ignorecase_both_sides", test_extract_ignorecase_both_sides),
        ("let_shadow_and_bind_once", test_let_shadow_and_bind_once),
        ("let_out_of_scope_binding_expr_rejected", test_let_out_of_scope_binding_expr_rejected),
        ("let_earlier_binding_not_visible_to_prior", test_let_earlier_binding_not_visible_to_prior),
        ("let_nested_inner_sees_outer", test_let_nested_inner_sees_outer),
        ("let_permissive_scope_admits_anything", test_let_permissive_scope_admits_anything),
        ("scope_unknown_top_vs_dotted_missing_subkey", test_scope_unknown_top_vs_dotted_missing_subkey),
        ("render_format_spec_coercion", test_render_format_spec_coercion),
        ("render_bad_spec_located", test_render_bad_spec_located),
        ("render_missing_modes_precise", test_render_missing_modes_precise),
        ("render_non_simple_hole_modes", test_render_non_simple_hole_modes),
        ("render_literal_braces_and_empty", test_render_literal_braces_and_empty),
        ("render_spec_split_with_colon_in_extract_slice", test_render_spec_split_with_colon_in_extract_slice),
        ("coalesce_edge_values", test_coalesce_edge_values),
        ("if_truthiness_edge", test_if_truthiness_edge),
        ("where_pred_references_row_column", test_where_pred_references_row_column),
        ("node_of_boundaries", test_node_of_boundaries),
        ("node_of_bad_byte_columns_skipped", test_node_of_bad_byte_columns_skipped),
        ("lookup_and_unique_edges", test_lookup_and_unique_edges),
    ]))
