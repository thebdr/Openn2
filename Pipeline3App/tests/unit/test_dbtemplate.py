"""Gate (data-independent): the two DB-config grammars in domain/dbtemplate.py.

`render` (PEP-3101 templates, numeric coercion, validate-and-raise) + `compile_for_each` (the iteration
DSL: row / unique / where predicates; parse errors raise). Both raise DbTemplateError -> the pipeline halt.
"""
from _harness import run, eq, ok

from pipeline3.domain import dbtemplate as T


def _raises(fn):
    try:
        fn()
        return False
    except T.DbTemplateError:
        return True


# --- render ------------------------------------------------------------------------------------- #
def test_render_format_specs():
    eq(T.render("S1.CABINET{cabinet:03d}.STATE", {"cabinet": "1"}), "S1.CABINET001.STATE", "int pad on a str cell")
    eq(T.render("{cabinet:03d}", {"cabinet": "12"}), "012")
    eq(T.render("[{device:>5}]", {"device": "ab"}), "[   ab]", "string align spec, no coercion")
    eq(T.render("{a}-{b}", {"a": "x", "b": "y"}), "x-y", "plain fields")
    eq(T.render("literal only", {}), "literal only")


def test_render_validation_raises():
    ok(_raises(lambda: T.render("{missing}", {"x": "1"})), "unknown field -> raise")
    ok(_raises(lambda: T.render("{x:03d}", {"x": "abc"})), "non-numeric value for :d -> raise")
    ok(_raises(lambda: T.render("{0}", {})), "positional field -> raise")
    eq(T.template_fields("S1.CABINET{cabinet:03d}.{role}"), {"cabinet", "role"}, "fields extracted")


# --- for_each: heads ---------------------------------------------------------------------------- #
def _r(**kw):
    return dict(kw)


def test_for_each_literal_and_row():
    fe = T.compile_for_each("")
    eq(list(fe.evaluate([_r(a=1), _r(a=2)])), [({}, None)], "blank -> one literal item, no row")
    fe = T.compile_for_each("row")
    rows = [_r(a="1"), _r(a="2")]
    eq([rep for _b, rep in fe.evaluate(rows)], rows, "row -> one per row")


def test_for_each_row_where():
    fe = T.compile_for_each('row where script_type in ["DI1/2","DI"]')
    rows = [_r(script_type="DI1/2"), _r(script_type="KQ"), _r(script_type="DI")]
    got = [rep["script_type"] for _b, rep in fe.evaluate(rows)]
    eq(got, ["DI1/2", "DI"], "in-set filter")
    eq(fe.columns, {"script_type"}, "referenced columns tracked")


def test_for_each_unique():
    fe = T.compile_for_each("cabinet in unique(diag_cabinet)")
    rows = [_r(diag_cabinet="1", x="a"), _r(diag_cabinet="2"), _r(diag_cabinet="1", x="b")]
    out = list(fe.evaluate(rows))
    eq([b["cabinet"] for b, _r2 in out], ["1", "2"], "distinct, first-seen order")
    eq(out[0][1]["x"], "a", "representative row = the first with that value")


def test_for_each_unique_numeric_skips_negative_and_blank():
    fe = T.compile_for_each("cabinet in unique(diag_cabinet) where numeric(diag_cabinet)")
    rows = [_r(diag_cabinet="1"), _r(diag_cabinet="-1"), _r(diag_cabinet=""), _r(diag_cabinet="2"), _r(diag_cabinet="1")]
    eq([b["cabinet"] for b, _ in fe.evaluate(rows)], ["1", "2"], "numeric() keeps positive ints only")


def test_for_each_unique_multivalue_splits():
    fe = T.compile_for_each("area in unique(matrix_areas)")
    rows = [_r(matrix_areas="AREA 1|AREA 2"), _r(matrix_areas="AREA 2|AREA 3")]
    eq([b["area"] for b, _ in fe.evaluate(rows)], ["AREA 1", "AREA 2", "AREA 3"], "|-split, distinct")


# --- for_each: predicate algebra ---------------------------------------------------------------- #
def test_for_each_predicates():
    rows = [_r(t="A", n="1"), _r(t="B", n="2"), _r(t="A", n="3")]
    keep = lambda expr: [r["n"] for _b, r in T.compile_for_each(expr).evaluate(rows)]
    eq(keep('row where t = "A"'), ["1", "3"], "equals")
    eq(keep('row where t != "A"'), ["2"], "not-equals")
    eq(keep('row where t = "A" and numeric(n)'), ["1", "3"], "and")
    eq(keep('row where t = "B" or n = "3"'), ["2", "3"], "or")
    eq(keep('row where not t = "A"'), ["2"], "not")
    eq(keep('row where (t = "A" or t = "B") and not n = "2"'), ["1", "3"], "parens + precedence")
    eq(keep('row where t ~ /A|B/'), ["1", "2", "3"], "regex")


def test_for_each_syntax_errors_raise():
    for bad in ("cabinet in unique(diag_cabinet", "x in foo(y)", 'row where t = bare',
                "cabinet unique(diag_cabinet)", "row where t == \"A\"", "nonsense @@@"):
        ok(_raises(lambda b=bad: T.compile_for_each(b)), f"{bad!r} -> raise")


if __name__ == "__main__":
    raise SystemExit(run("dbtemplate", [
        ("render_format_specs", test_render_format_specs),
        ("render_validation_raises", test_render_validation_raises),
        ("for_each_literal_and_row", test_for_each_literal_and_row),
        ("for_each_row_where", test_for_each_row_where),
        ("for_each_unique", test_for_each_unique),
        ("for_each_unique_numeric_skips_negative_and_blank", test_for_each_unique_numeric_skips_negative_and_blank),
        ("for_each_unique_multivalue_splits", test_for_each_unique_multivalue_splits),
        ("for_each_predicates", test_for_each_predicates),
        ("for_each_syntax_errors_raise", test_for_each_syntax_errors_raise),
    ]))
