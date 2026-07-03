"""The phase-520 template + for_each DSL engine (domain.dbtemplate) - pure, data-independent."""
from _harness import run, eq, ok, raises
from pipeline4.domain.dbtemplate import (
    DbTemplateError, render, template_fields, compile_for_each,
)


# --- 1. render (PEP-3101, bare fields, numeric coercion) ----------------------------------------- #
def test_render_bare_field():
    eq(render("Door [ {$combined_FLD} ]", {"combined_FLD": "S1-B1"}), "Door [ S1-B1 ]")
    eq(render("{$a} {$b}", {"a": "x", "b": "y"}), "x y")
    eq(render(None, {}), "", "None template -> ''")


def test_render_numeric_coercion():
    eq(render("S1.CABINET{$cabinet:03d}.STATE", {"cabinet": "1"}), "S1.CABINET001.STATE",
       "an integer spec coerces the string cell '1' -> 1 -> '001'")
    eq(render("{$n:02d}", {"n": "7"}), "07")
    eq(render("{$x:.1f}", {"x": "3"}), "3.0", "a float spec coerces too")


def test_render_errors():
    raises(DbTemplateError, lambda: render("{$missing}", {"a": "1"}))     # unknown field (expr strict)
    raises(DbTemplateError, lambda: render("{0}", {"a": "1"}))            # not a {$name} reference
    raises(DbTemplateError, lambda: render("{missing}", {"a": "1"}))      # forgot the $ -> guard rejects
    raises(DbTemplateError, lambda: render("{$cabinet:03d}", {"cabinet": "x"}))  # bad numeric coercion


def test_template_fields():
    eq(template_fields("a {x} b {y:03d} c"), {"x", "y"})
    eq(template_fields("no fields"), set())


# --- 2. the for_each DSL ------------------------------------------------------------------------- #
_ROWS = [
    {"script_type": "DI1/2", "diag_cabinet": "1", "fld": "A"},
    {"script_type": "DI2/2", "diag_cabinet": "1", "fld": "B"},
    {"script_type": "DD", "diag_cabinet": "2", "fld": "C"},
    {"script_type": "KQ", "diag_cabinet": "", "fld": "D"},
]


def _items(expr, rows=_ROWS):
    return list(compile_for_each(expr).evaluate(rows))


def test_for_each_literal():
    items = _items("")
    eq(items, [({}, None)], "(blank) -> one literal item")


def test_for_each_row_unfiltered():
    items = _items("row")
    eq(len(items), 4, "row -> one per row")
    eq([r["fld"] for _, r in items], ["A", "B", "C", "D"], "in input order")


def test_for_each_row_where_eq():
    items = _items("row where $script_type = 'DI1/2'")
    eq([r["fld"] for _, r in items], ["A"], "= filters to the exact match")


def test_for_each_row_where_in():
    items = _items("row where $script_type in ['DI1/2','DI2/2','DD']")
    eq([r["fld"] for _, r in items], ["A", "B", "C"], "in [..] is an OR over the listed values")


def test_for_each_row_where_numeric():
    items = _items("row where numeric($diag_cabinet)")
    eq([r["fld"] for _, r in items], ["A", "B", "C"], "numeric() keeps the digit cells, drops the blank")


def test_for_each_row_where_neq_and_regex():
    eq([r["fld"] for _, r in _items("row where $script_type != 'KQ'")], ["A", "B", "C"])
    eq([r["fld"] for _, r in _items("row where $script_type ~ /^DI/")], ["A", "B"], "~ is a regex search")


def test_for_each_row_where_boolean_combinators():
    items = _items("row where numeric($diag_cabinet) and not ($script_type = 'DD')")
    eq([r["fld"] for _, r in items], ["A", "B"], "and / not compose")
    items = _items("row where $script_type = 'KQ' or $diag_cabinet = '2'")
    eq([r["fld"] for _, r in items], ["C", "D"], "or composes")
    items = _items("row where ($script_type = 'DI1/2' or $script_type = 'DD') and numeric($diag_cabinet)")
    eq([r["fld"] for _, r in items], ["A", "C"], "parentheses group")


def test_for_each_unique_distinct_first_seen():
    items = _items("cab in unique($diag_cabinet) where numeric($diag_cabinet)")
    eq([(b["cab"], r["fld"]) for b, r in items], [("1", "A"), ("2", "C")],
       "unique -> one per DISTINCT value, bound to the var, at its FIRST row, in first-seen order")


def test_for_each_unique_pipe_split():
    rows = [{"areas": "AREA 1|AREA 2"}, {"areas": "AREA 2"}, {"areas": "AREA 3"}]
    items = _items("a in unique($areas)", rows)
    eq([b["a"] for b, _ in items], ["AREA 1", "AREA 2", "AREA 3"],
       "a |-multi-valued cell is split; duplicates across rows collapse")


def test_for_each_unique_list_cell_flattens():
    # a JSON LIST cell (e.g. the staged matrix_areas) yields one candidate per ITEM - the
    # 02_COM/05_EM_STATE per-area element rows iterate `area in unique($matrix_areas)`.
    rows = [{"matrix_areas": ["AREA 1", "AREA 2"], "script_type": "KQ"},
            {"matrix_areas": ["AREA 2"], "script_type": "E1/2"},
            {"matrix_areas": [], "script_type": "KQ"},
            {"matrix_areas": ["AREA 3"], "script_type": "KQ"}]
    items = _items("area in unique($matrix_areas)", rows)
    eq([b["area"] for b, _ in items], ["AREA 1", "AREA 2", "AREA 3"],
       "list cells flatten; empties skip; first-seen order")
    filtered = _items("area in unique($matrix_areas) where $script_type = 'KQ'", rows)
    eq([b["area"] for b, _ in filtered], ["AREA 1", "AREA 2", "AREA 3"],
       "the where pre-filters ROWS, then the surviving rows' lists flatten")


# --- 3. parse errors (validate-and-halt) --------------------------------------------------------- #
def test_for_each_errors():
    raises(DbTemplateError, lambda: compile_for_each("row where $script_type ="))     # missing rhs
    raises(DbTemplateError, lambda: compile_for_each("row extra tokens"))             # bad head
    raises(DbTemplateError, lambda: compile_for_each("banana"))                       # not row/var-in-unique
    raises(DbTemplateError, lambda: compile_for_each("row where $script_type ~ /[/"))  # bad regex
    raises(DbTemplateError, lambda: compile_for_each("row where x @ y"))              # unexpected character


if __name__ == "__main__":
    import sys
    sys.exit(run("dbtemplate", [
        ("render_bare_field", test_render_bare_field),
        ("render_numeric_coercion", test_render_numeric_coercion),
        ("render_errors", test_render_errors),
        ("template_fields", test_template_fields),
        ("for_each_literal", test_for_each_literal),
        ("for_each_row_unfiltered", test_for_each_row_unfiltered),
        ("for_each_row_where_eq", test_for_each_row_where_eq),
        ("for_each_row_where_in", test_for_each_row_where_in),
        ("for_each_row_where_numeric", test_for_each_row_where_numeric),
        ("for_each_row_where_neq_and_regex", test_for_each_row_where_neq_and_regex),
        ("for_each_row_where_boolean_combinators", test_for_each_row_where_boolean_combinators),
        ("for_each_unique_distinct_first_seen", test_for_each_unique_distinct_first_seen),
        ("for_each_unique_pipe_split", test_for_each_unique_pipe_split),
        ("for_each_unique_list_cell_flattens", test_for_each_unique_list_cell_flattens),
        ("for_each_errors", test_for_each_errors),
    ]))
