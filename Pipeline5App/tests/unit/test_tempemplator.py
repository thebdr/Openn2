"""The Tempemplator text renderer (language/tempemplator.py): {expr} value holes + @-directive
structure - recursion, range + table-query loops, block conditionals, located errors. Closes with
the THREE WORKED EXAMPLES from the user's original VBA tool, rendered from the SHIPPED
chain_reactions/templates.yaml (the reference templates must actually work)."""
from _harness import run, eq, ok, raises
from pipeline5 import config
from pipeline5.language.tempemplator import TempemplatorError, render_template


def _render(body, ctx, extra=None):
    return render_template("t", {"t": body, **(extra or {})}, ctx)


def test_plain_lines_and_strict_holes():
    eq(_render("A {$x} B", {"x": "1"}), "A 1 B", "expr holes render")
    eq(_render("no holes", {}), "no holes", "a literal line passes through")
    try:
        _render("bad {$missing} here", {"x": "1"})
        ok(False, "a missing field must raise (strict - a typo is an authoring error)")
    except TempemplatorError as error:
        eq((error.template, error.line), ("t", 1), "the error is located")


def test_use_recursion_unknown_and_cycle():
    eq(_render("head\n@use inner\ntail", {}, extra={"inner": "IN"}), "head\nIN\ntail", "@use splices")
    eq(_render("@use a", {}, extra={"a": "@use b", "b": "deep"}), "deep", "@use nests")
    raises(TempemplatorError, lambda: _render("@use nope", {}))
    raises(TempemplatorError, lambda: _render("@use a", {}, extra={"a": "@use a"}))          # self-cycle
    raises(TempemplatorError, lambda: _render("@use a", {}, extra={"a": "@use b", "b": "@use a"}))
    raises(TempemplatorError, lambda: _render("@use rows", {}, extra={"rows": [{"f": "1"}]}))  # a ROW template


def test_for_range_inline_and_block():
    eq(_render("@for $i in 1..3: n{$i}", {}), "n1\nn2\nn3", "inline range loop, inclusive")
    eq(_render("@for $i in 1..{$n}: x{$i}", {"n": "2"}), "x1\nx2", "rendered range end")
    eq(_render("@for $i in 2..1: x{$i}", {}), "", "an empty range emits nothing")
    body = "@for $i in 1..2\nA{$i}\nB{$i}\n@end\ndone"
    eq(_render(body, {}), "A1\nB1\nA2\nB2\ndone", "block form loops its whole body")
    ctx = {"i": "outer"}
    eq(_render("@for $i in 1..1: {$i}\n{$i}", ctx), "1\nouter", "the loop var shadows then restores")
    raises(TempemplatorError, lambda: _render("@for $i in 1..2\nX", {}))       # block without @end
    raises(TempemplatorError, lambda: _render("@for $i in a..b: x", {}))       # non-numeric range
    raises(TempemplatorError, lambda: _render("@for i in 1..2: x", {}))        # var must be $-prefixed


def test_for_table_query():
    db = {"signals": [{"script_type": "PEC", "tag": "P1"}, {"script_type": "MOT", "tag": "M1"},
                      {"script_type": "PEC", "tag": "P2"}]}
    eq(_render("@for $r in signals where $script_type = \"PEC\": -{$r.tag}", {"_db": db}),
       "-P1\n-P2", "the where() filter picks matching rows; fields via $var.field")
    eq(_render("@for $r in signals: {$r.tag}", {"_db": db}), "P1\nM1\nP2", "no where = every row")
    raises(TempemplatorError, lambda: _render("@for $r in nope: x", {"_db": db}))
    raises(TempemplatorError, lambda: _render("@for $r in signals maybe: x", {"_db": db}))


def test_if_else_and_lazy_branches():
    body = "@if $x = \"1\"\nYES\n@else\nNO\n@end"
    eq(_render(body, {"x": "1"}), "YES")
    eq(_render(body, {"x": "2"}), "NO")
    eq(_render("@if $x = \"1\"\nYES\n@end", {"x": "2"}), "", "no @else -> nothing")
    # THE conditional's point: the untaken branch is NEVER evaluated (a strict hole in it is safe)
    guarded = "@if present($maybe)\nval={$maybe}\n@else\nabsent\n@end"
    eq(_render(guarded, {"maybe": ""}), "absent", "the guarded strict hole did not evaluate")
    # the refuter-grade pin: a hole that WOULD raise (absent field), an unknown @use, and an
    # unknown-table @for inside the untaken branch - an EAGER renderer dies on each of these
    eq(_render('@if $x = "1"\n{$totally_missing}\n@else\nOK\n@end', {"x": "2"}), "OK",
       "an absent-field hole in the untaken branch never evaluates")
    eq(_render('@if $x = "1"\n@use no_such_template\n@else\nOK\n@end', {"x": "2"}), "OK",
       "an unknown @use in the untaken branch never resolves")
    eq(_render('@if $x = "1"\n@for $r in no_table\nz\n@end\n@else\nOK\n@end', {"x": "2"}), "OK",
       "an unknown-table block @for in the untaken branch never iterates")
    nested = "@if $a = \"1\"\n@if $b = \"1\"\nAB\n@else\nA-\n@end\n@end"
    eq(_render(nested, {"a": "1", "b": "0"}), "A-", "@if nests")
    raises(TempemplatorError, lambda: _render("@if $x = \"1\"\nY", {"x": "1"}))    # no @end
    raises(TempemplatorError, lambda: _render("@end", {}))                          # stray terminator
    raises(TempemplatorError, lambda: _render("@else", {}))
    raises(TempemplatorError, lambda: _render("@for $i in 1..1\n@else\n@end", {}))  # @else in a @for
    raises(TempemplatorError, lambda: _render("@nope stuff", {}))                   # unknown directive


def _error_line(body, ctx, extra=None):
    """The template-absolute line a failure reports (refuter round 5: nested blocks used to report
    slice-relative lines - a typo in a real nested template mislocated)."""
    try:
        _render(body, ctx, extra=extra)
    except TempemplatorError as error:
        return error.line
    raise AssertionError("expected a TempemplatorError")


def test_errors_locate_true_template_lines():
    eq(_error_line('@if $x = "1"\nliteral ok\n{$missing}\n@end', {"x": "1"}), 3,
       "a strict hole inside a taken @if reports ITS line, not the slice-relative one")
    eq(_error_line('@if $x = "1"\nA\n@else\n{$missing}\n@end', {"x": "2"}), 4,
       "an @else-branch error reports its true line")
    eq(_error_line("top\n@for $i in 1..1\n@use nope\n@end", {}), 3,
       "an unknown @use inside a @for block reports its true line")
    eq(_error_line("one\ntwo\n@for $i in 1..1: {$missing}", {}), 3,
       "an inline @for body error points at the @for line itself")
    eq(_error_line('@if $a = "1"\n@if $b = "1"\nok\n{$missing}\n@end\n@end', {"a": "1", "b": "1"}), 4,
       "doubly nested blocks still locate the absolute line")


def test_shipped_worked_examples_render():
    """The three REFERENCE templates shipped in the Siemens chain_reactions/templates.yaml are the
    VBA Tempemplator worked examples - they must render for real (the authoring manual is executable)."""
    templates = config.load_reaction_templates()
    for name in ("IN_Photocell", "StandardBelt", "Call_ConveyorManager"):
        ok(name in templates, f"shipped template {name} present")
    belt = {"LineName": "L01", "BeltName": "BELT_07", "NumPhotocells": "2",
            "PecInputTag": "\"PEC_07\"", "ConveyorPecA": ""}
    out = render_template("StandardBelt", templates, dict(belt))
    eq(out.splitlines()[0], "REGION BELT_07", "Ex.2: the region header")
    eq(sum(1 for line in out.splitlines() if line.startswith('"CONFIGURATION_IO".L01.BELT_07.PEC')), 2,
       "Ex.2 -> Ex.1: the counted loop expanded one photocell line per index")
    ok('PEC1."PEC-Input"' in out and 'PEC2."PEC-Input"' in out, "Ex.1: the loop var reached the text")
    ok("PecA := FALSE," in out, "Ex.3: the empty-field branch of the inline conditional")
    with_pec = render_template("Call_ConveyorManager", templates, {"ConveyorPecA": "PEC_A1"})
    eq(with_pec, 'PecA := "CONFIGURATION_IO".PEC_A1."PEC-Control-Out",',
       "Ex.3: the present-field branch wires the full binding")


if __name__ == "__main__":
    import sys
    sys.exit(run("tempemplator", [
        ("plain_lines_and_strict_holes", test_plain_lines_and_strict_holes),
        ("use_recursion_unknown_and_cycle", test_use_recursion_unknown_and_cycle),
        ("for_range_inline_and_block", test_for_range_inline_and_block),
        ("for_table_query", test_for_table_query),
        ("if_else_and_lazy_branches", test_if_else_and_lazy_branches),
        ("errors_locate_true_template_lines", test_errors_locate_true_template_lines),
        ("shipped_worked_examples_render", test_shipped_worked_examples_render),
    ]))
