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


def test_loop_row_columns_are_schema_checked():
    """B5 (refuter round 6), resolved against C-002 by the implications check: inside a TABLE loop,
    `{$r.column}` must name a column the table's rows carry - `{$r.tagg}` used to render a silent
    blank, so every row-field typo in an E3 loop was invisible. It is a SCHEMA check, not a data
    check: a column that is EMPTY on some rows is fine, and deeper JSON sub-keys / `_params` keys
    stay optional (C-002 silent-empty) so the guard idioms keep working."""
    db = {"signals": [{"script_type": "PEC", "tag": "P1", "type": {"type_id": "PEC"}},
                      {"script_type": "", "tag": "", "type": None}]}               # a node row: empty cells
    eq(_render("@for $r in signals: -{$r.tag}-", {"_db": db}), "-P1-\n--", "a real column renders (blank on the node row)")
    try:
        _render("line one\n@for $r in signals: -{$r.tagg}-", {"_db": db})
        ok(False, "a misspelled column must raise")
    except TempemplatorError as error:
        eq(error.line, 2, "the column typo locates its line")
        ok("'tagg'" in error.message and "tag" in error.message, "…names it and lists the real columns")
    eq(_render("@for $r in signals: [{$r.type.type_id}]", {"_db": db}), "[PEC]\n[]",
       "a JSON sub-key is OPTIONAL (blank on the node row whose `type` is empty)")
    eq(_render('@for $r in signals: {coalesce($r.type.tristate, "0")}', {"_db": db}), "0\n0",
       "the guard functions still work on optional sub-keys")
    body = "@for $r in signals\n@if present($r.type.type_id)\nT={$r.type.type_id}\n@end\n@end"
    eq(_render(body, {"_db": db}), "T=PEC", "the @if present(...) guard idiom")
    raises(TempemplatorError, lambda: _render("@for $i in 1..2: {$i.x}", {}))       # a range var has no columns
    eq(_render("@for $r in signals: @use leaf", {"_db": db}, extra={"leaf": "{$r.tag}"}), "P1\n",
       "the schema travels into an @use'd template")
    raises(TempemplatorError, lambda: _render("@for $r in signals: @use leaf", {"_db": db},
                                              extra={"leaf": "{$r.tagg}"}))
    eq(_render("@for $r in signals: x\n{$r.anything}", {"_db": db, "r": {"k": 1}}), "x\nx\n",
       "after the loop the outer `r` is plain data again (the schema shadowed, then restored)")
    # the check is PARSED (refuter round 9): a data-function predicate's `$type.type_id` is the SIGNALS
    # row's column, and a let-bound `$r` is local - neither is the loop row, whatever their names
    both = {"types": [{"type": "PEC", "desc": "photocell"}],          # NO type_id column in `types`
            "signals": [{"tag": "S1", "type": {"type_id": "P"}}]}
    eq(_render('@for $type in types: {count(signals, $type.type_id = "P")}', {"_db": both}), "1.0",
       "a predicate column that shares the loop var's name is not a loop-row column")
    eq(_render('@for $r in signals: {let(r := first(types, $type = "PEC"); $r.desc)}', {"_db": both}),
       "photocell", "a let binding that shadows the loop var is not the loop row")
    raises(TempemplatorError, lambda: _render("@for $r in signals: {$r.tagg}", {"_db": both}))   # still caught
    layered = {"_params": {"project_code": "8XXX"}, "_rule": {"name": "r", "hook": "after_300"}}
    eq(_render("[{$_params.project_code}] [{$_params.optional.key}]", layered), "[8XXX] []",
       "`_params` keys are optional by design (C-004 get_param) - absent reads blank")


def test_raw_errors_become_located():
    """B1 (refuter round 6): inputs that raised RAW exceptions (OverflowError, ValueError,
    re.PatternError) out of the renderer - each a located TempemplatorError now."""
    for n in ("inf", "-inf", "nan"):
        raises(TempemplatorError, lambda: _render("@for $i in 1..{$n}: x{$i}", {"n": n}))
    eq(_render("@for $i\tin 1..2: x{$i}", {}), "x1\nx2", "a TAB before `in` is whitespace like any other")
    # range ends are WHOLE numbers (refuter round 9): a `1...3` typo (-> '.3') used to render nothing,
    # a 2.7 was silently truncated, and 1..1e308 escaped raw
    eq(_render("@for $i in 1..{$n}: x{$i}", {"n": "2.0"}), "x1\nx2", "an integer-valued float (Excel's 2.0) is fine")
    # a BLANK end (an empty cell) is an EMPTY range - user decision 2026-09-25 (refuter round 10: it read
    # as 0, and a byte map invented a `QB0` for input-only nodes whose Q start/end are blank)
    eq(_render("@for $b in {$a}..{$z}: QB{$b}", {"a": "", "z": ""}), "", "blank..blank: no invented QB0")
    eq(_render("@for $i in 1..{$n}: x{$i}", {"n": ""}), "", "a blank count (Ex.2's NumPhotocells) emits nothing")
    eq(_render("@for $i in {$a}..3: x{$i}", {"a": ""}), "", "a blank START is empty too - not 0..3")
    eq(_render("@for $i in 1..{$n}: x{$i}", {"n": "  "}), "", "whitespace is blank")
    raises(TempemplatorError, lambda: _render("@for $i in ..3: x", {}))       # a MISSING end is a syntax slip
    # refuter round 11 (the code held; these pin it): a missing TAIL too, inline and block
    raises(TempemplatorError, lambda: _render("@for $i in 1..: x", {}))
    raises(TempemplatorError, lambda: _render("@for $i in 1..\nx\n@end", {}))
    # a malformed end is an error EVEN beside a blank one (every non-blank end is validated first)
    raises(TempemplatorError, lambda: _render("@for $i in abc..{$n}: x", {"n": ""}))
    # the loop-column check guards the RANGE ENDS too - since a blank end is an empty range, a typo'd
    # `$row.column` there would otherwise be a SILENT empty range (round 11's top hole)
    nodes = {"nodes": [{"Q_startByte": "4", "Q_endByte": "5"}]}
    raises(TempemplatorError, lambda: _render("@for $r in nodes\n@for $b in {$r.Q_startBytee}..{$r.Q_endByte}: x\n@end",
                                              {"_db": nodes}))
    raises(TempemplatorError, lambda: _render("@for $r in nodes: @for $b in {$r.Q_startBytee}..3: x", {"_db": nodes}))
    eq(_render("@for $r in nodes\n@for $b in {$r.Q_startByte}..{$r.Q_endByte}: QB{$b}\n@end", {"_db": nodes}),
       "QB4\nQB5", "the correct column iterates")
    # an inline `:` with an EMPTY body (a Python habit: the body on the next lines) is an error
    raises(TempemplatorError, lambda: _render("@for $i in 1..2:\n  x", {}))
    # a loop var that did not exist before the loop is GONE after it (a later {$i} is missing, not the
    # last value)
    raises(TempemplatorError, lambda: _render("@for $i in 1..2: x\n{$i}", {}))
    eq(_render("@for $b in {$a}..{$z}: QB{$b}", {"a": "0", "z": "1"}), "QB0\nQB1", "real ends still iterate")
    for bad in ("1...3", "1..2.7", "1..1e308"):
        raises(TempemplatorError, lambda: _render(f"@for $i in {bad}: x", {}))
    eq(_render("@for $i in\t1..2: x{$i}", {}), "x1\nx2", "…after `in` too")
    eq(_render("@for $i  in  1..2: x{$i}", {}), "x1\nx2", "…and any AMOUNT of it (round 12)")
    raises(TempemplatorError, lambda: _render("@for $1x in 1..2: x", {}))   # not a referenceable var
    db = {"signals": [{"tag": "P1"}]}
    raises(TempemplatorError, lambda: _render("{extract($tag, /(P/)}", {"tag": "P1"}))
    raises(TempemplatorError, lambda: _render("@for $r in signals where $tag ~ /(/: x", {"_db": db}))
    raises(TempemplatorError, lambda: _render("@if $tag ~ /[/\nx\n@end", {"tag": "P1"}))
    # the evaluation backstops: an input that blows expr's recursion is still LOCATED (round 8 EH4)
    deep = "not " * 1500 + '"x"'
    raises(TempemplatorError, lambda: _render("{" + deep + "}", {}))
    raises(TempemplatorError, lambda: _render("@if " + deep + "\nx\n@end", {}))


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
    eq(_render("@for $i in {$a}..3: x{$i}", {"a": "2"}), "x2\nx3",
       "rendered range START too (refuter round 6 E5: an unrendered start survived)")
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
    # a /regex/ in the predicate is ONE literal - its `..` is not a range, its `:` not the inline
    # body (refuter round 7 B5: `/^P..1$/` failed as "range ends must be finite numbers")
    tags = {"signals": [{"tag": "PEC1"}, {"tag": "PXY1"}, {"tag": "M1"}, {"tag": "a:b"}]}
    eq(_render("@for $r in signals where $tag ~ /^P..1$/: {$r.tag}", {"_db": tags}), "PEC1\nPXY1",
       "a `..` inside the regex (inline form)")
    eq(_render("@for $r in signals where $tag ~ /^P..1$/\n={$r.tag}\n@end", {"_db": tags}), "=PEC1\n=PXY1",
       "…and in the block form")
    eq(_render("@for $r in signals where $tag ~ /a:b/: {$r.tag}", {"_db": tags}), "a:b",
       "a `:` inside the regex is not the inline-body colon")
    # call arguments are opaque too - a slice `0:1`, a `let(n := ...)` (refuter round 8 R1)
    num = {"signals": [{"tag": "P12"}, {"tag": "M21"}, {"tag": "P13"}]}
    sliced = 'where extract($tag, /(\\d+)/, 0:1) = "1"'
    eq(_render(f"@for $r in signals {sliced}: {{$r.tag}}", {"_db": num}), "P12\nP13", "a slice colon (inline)")
    eq(_render(f"@for $r in signals {sliced}\n={{$r.tag}}\n@end", {"_db": num}), "=P12\n=P13", "…(block)")
    eq(_render(f'@if $x = "1"\n@for $r in signals {sliced}\n={{$r.tag}}\n@end\n@end', {"_db": num, "x": "1"}),
       "=P12\n=P13", "…(block, nested in an @if - the scan must not misread it as inline)")
    eq(_render('@for $r in signals where let(n := extract($tag, /(\\d+)/); $n = "21"): {$r.tag}', {"_db": num}),
       "M21", "a let binding's `:=`")
    # quotes, escapes and {holes} stay opaque (refuter round 8 EH1 - each was an unpinned mutant)
    quoted = {"signals": [{"tag": "a:b"}, {"tag": "a/b"}, {"tag": 'a"b'}]}
    eq(_render('@for $r in signals where $tag = "a:b": [{$r.tag}]', {"_db": quoted}), "[a:b]", "a double-quoted colon")
    eq(_render("@for $r in signals where $tag = 'a:b': [{$r.tag}]", {"_db": quoted}), "[a:b]", "a single-quoted colon")
    eq(_render("@for $r in signals where $tag ~ /a\\/b/: [{$r.tag}]", {"_db": quoted}), "[a/b]", "an escaped `/` in a regex")
    eq(_render('@for $r in signals where $tag = "a\\"b": [{$r.tag}]', {"_db": quoted}), '[a"b]', 'an escaped `"` in a string')
    eq(_render("@for $i in 1..{$n:d}: x{$i}", {"n": "2"}), "x1\nx2", "a format-spec colon inside a {hole}")
    # where() semantics: the predicate sees the ROW ONLY - an outer field is NOT in its scope, so
    # `$wanted` evaluates blank there (refuter round 6 E5: a leaking scope survived every test)
    rows = {"signals": [{"script_type": "", "tag": "E1"}, {"script_type": "PEC", "tag": "P1"}]}
    eq(_render("@for $r in signals where $script_type = $wanted: {$r.tag}", {"_db": rows, "wanted": "PEC"}),
       "E1", "the outer $wanted is invisible to the row predicate (it matched the blank row, not P1)")


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
    # the GRAMMAR is checked in the untaken branch too - laziness is about values (refuter round 12:
    # `@else if` silently read as a bare @else, the condition dropped: wrong branch, no finding)
    try:
        _render('@if $x = "1"\nA\n@else if $x = "2"\nB\n@end', {"x": "3"})
        ok(False, "`@else if` must raise")
    except TempemplatorError as error:
        eq(error.line, 3, "…at the @else line")
        ok("nest an @if" in error.message, "…telling the author how to write it")
    for slip in ('@if $x = "1"\nA\n@elif $x = "2"\nB\n@end',          # SCL's ELSIF habit, UNTAKEN
                 '@if $x = "1"\nA\n@elsif $x = "2"\nB\n@end',
                 '@if $x = "1"\nA\n@else @use other\n@end',
                 '@if $x = "1"\nA\n@end // done',
                 '@if $x = "1"\n@bogus\n@end',
                 "@if\nA\n@end"):                                     # a bare @if (no condition)
        raises(TempemplatorError, lambda: _render(slip, {"x": "2"}, extra={"other": "o"}))
    eq(_render('@if $x = "1"\nA\n@else\n@if $x = "2"\nB\n@end\n@end', {"x": "2"}), "B",
       "the else-if idiom: an @if nested in the @else")
    # refuter round 13: the same slips one level DEEPER, and the other grammar, in untaken branches
    for slip in ('@if $x = "1"\n@if $y = "1"\nA\n@elif $y = "2"\nB\n@end\n@end',
                 '@if $x = "1"\n@if $y = "1"\nA\n@else if $y = "2"\nB\n@end\n@end',
                 '@if $x = "1"\n@for $i in 1..2\nA\n@end // loop\n@end',
                 '@if $x = "1"\n@for i in 1..2: A\n@end',                # a malformed @for head
                 '@if $x = "1"\n@use\n@end',                             # a bare @use
                 '@if $x = "1"\n@for $r in signals where: A\n@end',      # a dangling `where`
                 '@if $x = "1"\n@for $i in 1..2: @usee leaf\n@end',      # an inline body's directive
                 '@if $x = "1"\n@if $y = "1"\nA\n@else\nB\n@else\nC\n@end\n@end'):   # a nested SECOND @else
        raises(TempemplatorError, lambda: _render(slip, {"x": "0", "y": "0"}))
    raises(TempemplatorError, lambda: _render("@for $i in 1..{$n}: @usee leaf", {"n": ""}))   # zero iterations too
    raises(TempemplatorError, lambda: _render("@for $r in signals where: {$r.tag}", {"_db": {"signals": []}}))
    # a misplaced @else in a NESTED block of an untaken branch (a forgotten inner @end): located at the
    # @else, never a silently dropped branch
    misclosed = 'CAB\n@if $swp = "Y"\n@for $s in signals\n  {$s.tag}\n@else\n  // no SWP\n@end\n@end'
    try:
        _render(misclosed, {"swp": "N", "_db": {"signals": []}})
        ok(False, "a nested misplaced @else must raise")
    except TempemplatorError as error:
        eq(error.line, 5, "…at the @else line")
    try:                                                    # and a never-closed block names the INNERMOST
        _render('@if $x = "1"\nA\n@for $i in 1..2\nB', {"x": "0"})
        ok(False, "a never-closed block must raise")
    except TempemplatorError as error:
        eq(error.line, 3, "…at the unclosed @for, not the outer @if (the author's real slip)")


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
    # refuter round 6 E4: every OTHER offset site, nested (at top level their offset is 0, so the
    # dropped-offset mutants survived) - each case below kills one surviving mutant
    eq(_error_line('@if $a = "1"\n@if $b = "1"\nX\n@else\n{$missing}\n@end\n@end', {"a": "1", "b": "0"}), 5,
       "a NESTED @else branch (M7)")
    eq(_error_line('@if $a = "1"\n@for $i in 1..1\nok\n{$missing}\n@end\n@end', {"a": "1"}), 4,
       "a @for BLOCK nested in an @if - the StandardBelt shape (M8)")
    eq(_error_line('@if $a = "1"\nx\n@for $i in 1..1: {$missing}\n@end', {"a": "1"}), 3,
       "an INLINE @for nested in an @if (M9)")
    eq(_error_line('@if $a = "1"\n@if $b = "1"\nX\n@else\nY\n@else\n@end\n@end', {"a": "1", "b": "1"}), 6,
       "a second @else found by the NESTED block scan (M10)")


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
        ("loop_row_columns_are_schema_checked", test_loop_row_columns_are_schema_checked),
        ("raw_errors_become_located", test_raw_errors_become_located),
        ("use_recursion_unknown_and_cycle", test_use_recursion_unknown_and_cycle),
        ("for_range_inline_and_block", test_for_range_inline_and_block),
        ("for_table_query", test_for_table_query),
        ("if_else_and_lazy_branches", test_if_else_and_lazy_branches),
        ("errors_locate_true_template_lines", test_errors_locate_true_template_lines),
        ("shipped_worked_examples_render", test_shipped_worked_examples_render),
    ]))
