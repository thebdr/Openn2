r"""The unified expression engine (core/expr): test / evaluate / render over the M-E1 grammar.

Covers the whole superset + the parity-critical cases vs rule_expr (extract -1: / :1, IGNORECASE at both
~ and extract, scope validation, dotted silent-empty, let bind-once, if/coalesce, the three render modes,
the format-spec coercion, the sentinel verbatim, clean(), and the data funcs over a synthetic tables dict).
"""
from _harness import run, eq, ok, raises
from pipeline4.core import expr
from pipeline4.core.expr import Scope, ExprError


# --- operators (rule_expr parity, $-fielded) ----------------------------------------------------- #
def test_regex_and_equality():
    ctx = {"desc": "EMERGENCY PUSH-BUTTON PRESSED", "type_hw": "DI", "addr": "I0.0"}
    ok(expr.test("$desc ~ /EMERGENCY PUSH.BUTTON PRES/", ctx), "ci regex search with . wildcard")
    eq(expr.test("$desc ~ /fire alarm/", ctx), False, "no match -> False")
    ok(expr.test('$type_hw = "DI"', ctx), "string equality")
    ok(expr.test('$type_hw != "XX"', ctx), "string inequality")
    ok(expr.test("$addr ~ /i/", ctx), "case-insensitive single letter")


def test_numeric_and_funcs():
    ok(expr.test("$id_node > 0", {"id_node": "3"}), "numeric > with coercion")
    eq(expr.test("$id_node > 0", {"id_node": ""}), False, "non-numeric -> comparison False")
    ok(expr.test("len($desc) > 3", {"desc": "ABCD"}), "len() > N")
    eq(expr.test("len($desc) > 3", {"desc": "AB"}), False, "len() short")
    ok(expr.test("numeric($x)", {"x": "12"}), "numeric() true")
    eq(expr.test("numeric($x)", {"x": "ab"}), False, "numeric() false")
    ok(expr.test("present($type_hw)", {"type_hw": "DI"}), "present() true")
    ok(expr.test("blank($type_hw)", {"type_hw": "   "}), "blank() true on whitespace")
    ok(expr.test("isdigit($x)", {"x": "12"}), "isdigit true")
    eq(expr.test("isdigit($x)", {"x": "1a"}), False, "isdigit false")


def test_boolean_composition():
    ctx = {"desc": "DOOR OPEN CH 1", "d2": "CH 1"}
    ok(expr.test("$desc ~ /DOOR.*OPEN/ and $d2 ~ /CH/", ctx), "and")
    ok(expr.test("$desc ~ /nope/ or $d2 ~ /CH/", ctx), "or")
    ok(expr.test("not $desc ~ /nope/", ctx), "not")
    ok(expr.test("($desc ~ /DOOR/ or $desc ~ /x/) and $d2 ~ /CH/", ctx), "parens")


def test_in_list():
    ok(expr.test('$script_type in ["KQ","KI"]', {"script_type": "KI"}), "in list membership")
    eq(expr.test('$script_type in ["KQ","KI"]', {"script_type": "DD"}), False, "not in list")


# --- extract: capture-first + slice (the former rule_expr `last` parity, now a fixed table) ------- #
def test_extract_last_slice_table():
    # `-1:` slices the whole match (no group) == the last char (rule_expr's old `last` semantics)
    for d2, pat, want in [("FOO CH7 BAR", "CH.", "7"), ("ENCODER CELL 4", r"CELL.\d", "4"),
                          ("EMERG RESET AREA 3", "AREA .", "3")]:
        eq(expr.evaluate("extract($d2, /%s/, -1:)" % pat, {"d2": d2}), want, "expr -1: last char on /%s/" % pat)
    eq(expr.evaluate("extract($d2, /CH./, -1:)", {"d2": "FOO CH7 BAR"}), "7", "last char")
    eq(expr.evaluate("extract($d2, /CH./, :1)", {"d2": "FOO CH7 BAR"}), "C", ":1 == first char")
    eq(expr.evaluate("extract($d2, /NOPE/, -1:)", {"d2": "xyz"}), "", "no match -> empty")


def test_extract_capture_first():
    eq(expr.evaluate("extract($f, /CH(\\d+)/)", {"f": "CH123"}), "123", "capture group(1) by default")
    eq(expr.evaluate("extract($f, /CH(\\d+)/, -1:)", {"f": "CH123"}), "3", "slice applies to the capture")
    eq(expr.evaluate("extract($f, /CH(\\d+)/, :2)", {"f": "CH123"}), "12", ":2 of the capture")
    eq(expr.evaluate("extract($f, /CH./, 1)", {"f": "xCHq"}), "H", "no group -> index 1 of group(0) 'CHq'")
    eq(expr.evaluate("extract($f, /CH(.)(.)/)", {"f": "CHab"}), "a", "capture-first uses group(1) only")


def test_regex_replace():
    eq(expr.evaluate("regex_replace($bit, /^I/, 'Q')", {"bit": "I13.5"}), "Q13.5", "prefix swap")
    eq(expr.evaluate(r"regex_replace($bit, /I(\d+)\.(\d+)/, 'Q\1.\2')", {"bit": "I13.5"}),
       "Q13.5", "\\1 group backrefs work (re.sub semantics)")
    eq(expr.evaluate("regex_replace($t, /o/, '0')", {"t": "foo boo"}), "f00 b00", "EVERY match replaces")
    eq(expr.evaluate("regex_replace($t, /BAR/, 'x')", {"t": "bar Bar"}), "x x", "implicit IGNORECASE")
    eq(expr.evaluate("regex_replace($t, /nope/, 'x')", {"t": "abc"}), "abc", "no match -> unchanged")
    eq(expr.evaluate("regex_replace(concat($a, '.', $b), /\\./, '_')", {"a": "1", "b": "2"}), "1_2",
       "the value arg is a full expression")
    eq(expr.evaluate("regex_replace($t, /x/, $r)", {"t": "x", "r": "Y"}), "Y",
       "the replacement arg is a full expression too")
    eq(expr.render("{regex_replace($bit, /^I/, 'Q')}", {"bit": "I2.0"}), "Q2.0",
       "usable in a render hole (the I->Q address-derivation case)")
    try:
        expr.evaluate(r"regex_replace($t, /x/, '\9')", {"t": "x"})
        ok(False, "a bad group backref must raise")
    except ExprError as e:
        ok("regex_replace" in str(e), f"located error: {e}")


def test_ignorecase_both():
    eq(expr.test("$d ~ /door/", {"d": "DOOR OPEN"}), True, "~ is IGNORECASE")
    eq(expr.evaluate("extract($d, /door(.)/)", {"d": "DOORX"}), "X", "extract is IGNORECASE")


# --- $field refs + scope + dotted ---------------------------------------------------------------- #
def test_field_basics_and_bareword():
    eq(expr.evaluate("$name", {"name": "abc"}), "abc", "$field ref")
    eq(expr.evaluate("$missing", {}), "", "missing field -> '' (permissive)")
    raises(ExprError, lambda: expr.evaluate("bareword", {}))
    raises(ExprError, lambda: expr.evaluate("foo(x)", {}))            # unknown func


def test_scope_validation():
    sc = Scope(["a", "b"])
    eq(expr.evaluate("$a", {"a": "1"}, scope=sc), "1", "known field passes")
    raises(ExprError, lambda: expr.evaluate("$x", {}, scope=sc))      # unknown -> compile error
    eq(expr.evaluate("$x", {}, scope=None), "", "scope=None -> silent ''")


def test_dotted_object_access():
    ctx = {"obj": {"key": "V", "sub": {"deep": "D"}}}
    eq(expr.evaluate("$obj.key", ctx), "V", "dotted into a dict cell")
    eq(expr.evaluate("$obj.sub.deep", ctx), "D", "two-level drill")
    eq(expr.evaluate("$obj.nokey", ctx), "", "missing sub-key -> '' (silent, no throw)")
    eq(expr.evaluate("$obj.key.x", ctx), "", "drill into a non-dict -> ''")
    # dotted under scope: only the TOP-LEVEL name is validated
    eq(expr.evaluate("$obj.key", ctx, scope=Scope(["obj"])), "V", "scope validates the top name only")


# --- concat / join / startswith / clean ---------------------------------------------------------- #
def test_string_funcs():
    eq(expr.evaluate('concat($a, "-", $b)', {"a": "x", "b": "y"}), "x-y", "concat")
    eq(expr.evaluate('join("/", $a, $b, $c)', {"a": "1", "b": "2", "c": "3"}), "1/2/3", "join")
    ok(expr.test('startswith($f, "PRE")', {"f": "PREFIX"}), "startswith true")
    eq(expr.test('startswith($f, "PRE")', {"f": "nope"}), False, "startswith false")


def test_clean():
    eq(expr.evaluate("clean($f)", {"f": "a\x00b\tc   d\n"}), "a b c d", "control chars + ws collapse + strip")
    eq(expr.evaluate("clean($f)", {"f": "  hi   there  "}), "hi there", "ws collapse")


def test_strip():
    eq(expr.evaluate("strip($f)", {"f": "  hi  there  "}), "hi  there", "strip trims ends but does NOT collapse")
    eq(expr.evaluate("strip($f)", {"f": "PA"}), "PA", "strip of a clean token is identity")
    eq(expr.render("{strip($t)}", {"t": " P  W "}), "P  W",
       "strip in a render hole keeps internal spaces (vs clean which would collapse)")


# --- single-quoted string literals (config CSVs avoid double-quote escaping) ---------------------- #
def test_single_quoted_strings():
    eq(expr.evaluate("'a'", {}), "a", "single-quoted string literal evaluates to its content")
    eq(expr.evaluate("join(' ', $a, $b)", {"a": "x", "b": "y"}), "x y", "single-quote as a join separator")
    ok(expr.test("$type_hw = 'DI'", {"type_hw": "DI"}), "single-quote as an = rhs")
    eq(expr.test("$type_hw = 'DI'", {"type_hw": "XX"}), False, "single-quote = rhs mismatch -> False")
    eq(expr.evaluate("'it\\'s'", {}), "it's", "escaped single-quote inside a single-quoted string")


# --- if / coalesce ------------------------------------------------------------------------------- #
def test_if_and_coalesce():
    eq(expr.evaluate('if($c, "Y", "N")', {"c": "1"}), "Y", "if true branch")
    eq(expr.evaluate('if($c, "Y", "N")', {"c": ""}), "N", "if false branch (empty)")
    # truthy semantics (rule_expr parity): a non-empty STRING is truthy, so "0" -> Y (it's a string, not 0)
    eq(expr.evaluate('if($c, "Y", "N")', {"c": "0"}), "Y", 'string "0" is non-empty -> truthy')
    eq(expr.evaluate("if(len($c) > 0, $c, \"none\")", {"c": ""}), "none", "numeric cond -> false branch")
    eq(expr.evaluate("coalesce($a, $b, $c)", {"a": "", "b": "", "c": "z"}), "z", "first non-empty")
    eq(expr.evaluate('coalesce($a, "0")', {"a": ""}), "0", '"0" is non-empty -> kept')
    eq(expr.evaluate("coalesce($a, $b)", {"a": "", "b": ""}), "", "all empty -> ''")


# --- let: sequential bind-once, shadowing, nesting ----------------------------------------------- #
def test_let():
    eq(expr.evaluate("let(a := $x ; $a)", {"x": "v"}), "v", "single bind")
    eq(expr.evaluate('let(a := $x, b := concat($a, "!") ; $b)', {"x": "hi"}), "hi!", "later sees earlier")
    eq(expr.evaluate("let(x := $x ; $x)", {"x": "raw"}), "raw", "bind shadows ctx (bind-once of the orig)")
    eq(expr.evaluate("let(a := $x ; let(b := concat($a, $a) ; $b))", {"x": "z"}), "zz", "nested let")
    # scope: a let-bound name is valid in the body even under a strict scope
    eq(expr.evaluate("let(a := $x ; $a)", {"x": "v"}, scope=Scope(["x"])), "v", "let-bound name admitted")
    raises(ExprError, lambda: expr.evaluate("let(a := $x ; $a)", {"x": "v"}, scope=Scope(["q"])))  # $x unknown


# --- render: holes / empty / format-spec --------------------------------------------------------- #
def test_render_basic():
    eq(expr.render("E{extract($d2,/CH./,-1:)}/2", {"d2": "FOO CH7 BAR"}), "E7/2", "extract hole + literal")
    eq(expr.render("{$t}", {"t": "PLC"}), "PLC", "field hole")
    eq(expr.render("KQ", {}), "KQ", "literal, no holes")
    eq(expr.render("{}", {}), "", "empty hole -> ''")
    eq(expr.render("{ }", {}), "", "blank hole -> ''")
    eq(expr.render("a{$x}b{$y}c", {"x": "1", "y": "2"}), "a1b2c", "multi-field + verbatim text")


def test_render_format_spec():
    eq(expr.render("{$n:03d}", {"n": "0"}), "000", "spec on '0' -> 000")
    eq(expr.render("{$n:03d}", {"n": 0}), "000", "spec on int 0 -> 000")
    eq(expr.render("{$n:03d}", {"n": ""}), "", "blank stays blank")
    eq(expr.render("{$n:03d}", {"n": "5"}), "005", "spec on '5'")
    eq(expr.render("{$f:.2f}", {"f": "1.5"}), "1.50", "float spec")
    eq(expr.render("{$f:.2f}", {"f": ""}), "", "blank float stays blank")


def test_render_missing_modes():
    eq(expr.render("{$x}", {}, mode="empty"), "", "empty: missing -> ''")
    eq(expr.render("{$x}", {}, mode="keep"), "{$x}", "keep: missing -> literal token")
    eq(expr.render("{$x}", {"x": ""}, mode="keep"), "", "keep: present-but-empty -> ''")
    raises(ExprError, lambda: expr.render("{$x}", {}, mode="strict"))
    eq(expr.render("{$x}", {"x": "ok"}, mode="strict"), "ok", "strict: present -> value")
    # a missing field NESTED in a function-call hole is also caught (the M-E5 strict-fidelity fix)
    raises(ExprError, lambda: expr.render("{concat($a, $missing)}", {"a": "x"}, mode="strict"))
    eq(expr.render("{concat($a, $missing)}", {"a": "x"}, mode="keep"), "{concat($a, $missing)}",
       "keep: a missing field in a function hole leaves the whole token")
    eq(expr.render("{concat($a, $b)}", {"a": "x", "b": "y"}, mode="strict"), "xy",
       "strict: all fields present in a function hole -> evaluates")
    eq(expr.render("{clean($d)}", {"d": "  z  "}, mode="strict"), "z", "strict: a present field under a func -> value")


def test_render_sentinel_verbatim():
    eq(expr.render("<input required>", {}), "<input required>", "sentinel verbatim (no holes)")
    eq(expr.render("plain text", {}), "plain text", "plain literal")


# --- data funcs over a synthetic tables dict ----------------------------------------------------- #
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


def test_data_funcs():
    ctx = _db()
    rows = expr.evaluate('where(signals, $type = "DI")', ctx)
    eq([r["name"] for r in rows], ["A", "B"], "where filters by per-row predicate")
    eq(expr.evaluate('first(signals, $type = "DO")', ctx)["name"], "C", "first match")
    eq(expr.evaluate('first(signals, $type = "ZZ")', ctx), {}, "first none -> {}")
    eq(expr.evaluate('lookup(signals, name, "B", bit)', ctx), "I1.0", "lookup")
    eq(expr.evaluate('lookup(signals, name, "ZZ", bit)', ctx), "", "lookup miss -> ''")
    eq(expr.evaluate("unique(type, signals)", ctx), ["DI", "DO"], "unique distinct first-seen")
    eq(expr.evaluate("count(signals)", ctx), 3.0, "count all")
    eq(expr.evaluate('count(signals, $type = "DI")', ctx), 2.0, "count filtered")


def test_node_of():
    ctx = _db()
    eq(expr.evaluate('node_of("I12.3", nodes)', ctx)["node"], "N2", "node owns byte 12 -> N2")
    eq(expr.evaluate('node_of("I3.0", nodes)', ctx)["node"], "N1", "byte 3 -> N1")
    eq(expr.evaluate('node_of("I99.0", nodes)', ctx), {}, "out of range -> {}")


# --- errors ------------------------------------------------------------------------------------- #
def test_errors_located():
    for bad in ("$d ~ notaregex", "len(", "foo($x)", "$d = ", "extract($d,/re/", "$d +"):
        raises(ExprError, lambda b=bad: expr.test(b, {"d": "x"}))


def test_cache_shares():
    # same text+scope id -> cached; different scope objects compile independently
    sc = Scope(["a"])
    eq(expr.evaluate("$a", {"a": "1"}, scope=sc), "1", "first")
    eq(expr.evaluate("$a", {"a": "2"}, scope=sc), "2", "cached re-eval, fresh ctx")


if __name__ == "__main__":
    import sys
    sys.exit(run("expr", [
        ("regex_and_equality", test_regex_and_equality),
        ("numeric_and_funcs", test_numeric_and_funcs),
        ("boolean_composition", test_boolean_composition),
        ("in_list", test_in_list),
        ("extract_last_slice_table", test_extract_last_slice_table),
        ("extract_capture_first", test_extract_capture_first),
        ("regex_replace", test_regex_replace),
        ("ignorecase_both", test_ignorecase_both),
        ("field_basics_and_bareword", test_field_basics_and_bareword),
        ("scope_validation", test_scope_validation),
        ("dotted_object_access", test_dotted_object_access),
        ("string_funcs", test_string_funcs),
        ("clean", test_clean),
        ("strip", test_strip),
        ("single_quoted_strings", test_single_quoted_strings),
        ("if_and_coalesce", test_if_and_coalesce),
        ("let", test_let),
        ("render_basic", test_render_basic),
        ("render_format_spec", test_render_format_spec),
        ("render_missing_modes", test_render_missing_modes),
        ("render_sentinel_verbatim", test_render_sentinel_verbatim),
        ("data_funcs", test_data_funcs),
        ("node_of", test_node_of),
        ("errors_located", test_errors_located),
        ("cache_shares", test_cache_shares),
    ]))
