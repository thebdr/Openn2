"""The template builder's engine doors (P-012): the Tempemplator's STATIC lint and the engine's
`lint` / `preview`. The contract under test is CONSUMER MATCH - the builder never approves what a
fire rejects:
  - every error the renderer raises, the lint finds on the SAME line (and more: an untaken branch);
  - in a rule's context the lint finds what the strict render would raise for that rule;
  - a preview IS the fire minus the side effects: the same rows, the same file text and path, the
    same finding (type + detail).
Hermetic: synthetic templates / tables; fire writes into temp dirs."""
import os
import tempfile

from _harness import run, eq, ok
from pipeline5 import config
from pipeline5.config.params import _read_yaml
from pipeline5.language.tempemplator import TempemplatorError, lint, lint_line, render_template
from pipeline5.phases.chain_reactions import engine
from pipeline5.truth.database import Database
from pipeline5.truth.table import Table

_SHIPPED = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                        "pipeline5", "systems", "plc_based", "siemens_s7", "safety", "config_project",
                        "chain_reactions", "templates.yaml")

# (body, the line the RENDERER reports) - each a TempemplatorError when rendered with _CTX
_BROKEN = [
    ("@if\nx\n@end", 1),                                   # a bare @if
    ("ok\n@elif $a", 2),                                   # an unknown directive
    ("@else", 1),                                          # @else without an open block
    ("x\n@end", 2),                                        # @end without an open block
    ("@if $a\nx", 1),                                      # never closed
    ("@if $a\n@if $b\nx\n@end", 1),                        # the OUTER is the unclosed one
    ("@if $a\n@for $i in 1..2\nx\n@end", 1),
    ("@for $i in 1..2\nx", 1),
    ("@for $i in 1..2: ", 1),                              # an empty inline body
    ("@for $i in 1..2: @if $a", 1),                        # an inline block directive
    ("@for $i in ..2: x", 1),                              # a missing range end
    ("@for $i in 1..abc: x", 1),                           # a non-numeric literal end
    ("@for $i in 1..2.5: x", 1),                           # a non-integer literal end
    ("@for $r in signals wherever $x: y", 1),              # `where` is a whole word
    ("@for $r in signals where: y", 1),                    # a dangling where
    ("@for x in signals: y", 1),                           # a malformed head
    ("@use nope", 1),                                      # an unknown template
    ("@use rows", 1),                                      # a ROW template is not text
    ("@use t", 1),                                         # a cycle
    ("x {$a +} y", 1),                                     # a hole that does not compile
    ("a } b", 1),                                          # a lone brace
    ("@if $a = \"1\"\nA\n@else\nB\n@else\nC\n@end", 5),     # a second @else
    ("@for $i in 1..2\n@else\n@end", 2),                   # @else in a @for
    ("@if $a\nA\n@else if $b\nB\n@end", 3),                # there is no `@else if`
    ("@if $a ~ /(/\nx\n@end", 1),                          # a malformed regex predicate
    ("PEC{:03d}();", 1),                                   # a spec with no expression (C-025 round 1)
    ("x {$a:03D}", 1),                                     # a spec no value satisfies (round 1)
]
_CTX = {"a": "1", "b": "1", "_db": {"signals": []}}


def _errors(problems, template="t"):
    return {p.where for p in problems if p.template == template and p.severity == "error"}


def test_lint_finds_every_render_error_on_its_line():
    """The core consumer match: for each broken template the renderer raises at line L - and the
    lint, run with NO context, reports an error on line L."""
    for body, line in _BROKEN:
        templates = {"t": body, "rows": [{"a": "b"}]}
        try:
            render_template("t", templates, dict(_CTX))
            ok(False, f"{body!r} must fail to render (the case is miswritten)")
        except TempemplatorError as error:
            eq(error.line, line, f"{body!r}: the renderer's line")
        ok(line in _errors(lint(templates)), f"{body!r}: the lint reports line {line} "
                                             f"(got {sorted(lint(templates))})")


def test_lint_walks_every_branch():
    """What the lint adds over a render: an UNTAKEN branch's problems. The render succeeds (its
    values are never evaluated), the lint still reports them - and, in a rule's context, a field the
    branch reads that the rule's rows do not carry."""
    body = '@if $a = "1"\nok\n@else\n{$b +} {$missing}\n@end'
    eq(render_template("t", {"t": body}, {"a": "1"}), "ok", "the taken branch renders")
    eq(_errors(lint({"t": body})), {4}, "the untaken branch's malformed hole is still found")
    context = lint({"t": body}, start="t", fields={"a", "b", "_params", "_rule", "_db"})
    ok(any(p.where == 4 and "$missing" in p.message for p in context), "…and, in context, its missing field")
    eq(lint({"t": "@if $a\nA\n@else\n@use t2\n@end", "t2": "{$x}"}), [], "a clean walk reports nothing")
    eq(_errors(lint({"t": "@if $a\n@if $b\nx"})), {2}, "two unclosed blocks: ONLY the innermost, as the renderer says")


def test_context_lint_matches_the_strict_render():
    """In a rule's context (the fields its rows carry + the hook's tables) the lint reports exactly
    what the strict render raises for that context - and a context-clean template renders."""
    fields = {"name", "n", "_params", "_rule", "_db"}
    tables = {"signals": ["uid", "tag", "type"]}
    ctx = {"name": "B1", "n": "2", "_params": {}, "_rule": {}, "_db": {"signals": [{"uid": "1", "tag": "P1", "type": ""}]}}
    cases = [
        ("{$nme}", 1, "missing field $nme"),
        ("@for $i in 1..{$count}: x", 1, "missing field $count"),          # a range end
        ("@for $r in signals\n{$r.tagg}\n@end", 2, "no column 'tagg'"),      # the loop-column check
        ("@for $i in 1..2: {$i.x}", 1, "a range variable is a number"),
        ("@for $r in things: x", 1, "unknown table 'things'"),
        ("@for $i in 1..{$n}: @use leaf", 1, "missing field $q"),            # carried into an @use
    ]
    for body, line, needle in cases:
        templates = {"t": body, "leaf": "{$i}{$q}"}
        try:
            render_template("t", templates, dict(ctx))
            ok(False, f"{body!r} must fail to render in this context")
        except TempemplatorError as error:
            ok(needle.split(" ")[-1].strip("'$") in error.message or needle in error.message,
               f"{body!r}: the render's own complaint ({error.message})")
        found = lint(templates, start="t", fields=fields, tables=tables)
        ok(any(needle in p.message and p.severity == "error" for p in found), f"{body!r}: the lint says {needle!r} ({found})")
        ok(any(p.where == line for p in found if needle in p.message) or needle == "missing field $q",
           f"{body!r}: on line {line}")
    clean = "REGION {$name}\n@for $i in 1..{$n}: @use leaf\n@for $r in signals where $tag = \"P1\"\n{$r.tag}\n@end"
    templates = {"t": clean, "leaf": "PEC{$i}"}
    eq(lint(templates, start="t", fields=fields, tables=tables), [], "a context-clean template")
    eq(render_template("t", templates, dict(ctx)), "REGION B1\nPEC1\nPEC2\nP1", "…renders")


def test_predicates_are_lenient_so_their_unknowns_are_warnings():
    """@if / `where` read an unknown name as blank - a WARNING, never an error; the classic slip is a
    `where` reading its own loop var (it sees the ROW's columns - C-024 refute round 16's note)."""
    found = lint({"t": '@for $s in signals where $s.tag = "P1"\nx\n@end\n@if $colour = "red"\ny\n@end'},
                 start="t", fields={"_params", "_rule", "_db"}, tables={"signals": ["uid", "tag"]})
    eq(sorted((p.where, p.severity) for p in found), [(1, "warning"), (4, "warning")], "two warnings, no error")
    ok("loop variable" in found[0].message and "$colour" in found[1].message, "each says why")
    eq(lint({"t": "@if $a\nx\n@end"}), [], "without a context an @if name is not judged")
    found = lint({"t": '@for $r in signals\n@if $r.tagg = "P1"\nX\n@end\n@end'}, start="t", fields={"_db"},
                 tables={"signals": ["uid", "tag"]})                 # C-025 round 1: a loop row's typo in an
    eq([(p.where, p.start, p.end, p.severity) for p in found], [(2, 4, 11, "warning")],   # @if reads blank
       "an @if reading a loop row's missing column")


def test_positions_point_at_the_culprit():
    """Columns into the RAW line (indentation kept): the builder squiggles the exact text."""
    eq(lint_line("A {$x}} B"), [(6, 7, "a lone '}' at column 7 of 'A {$x}} B' - write a literal brace "
                                       "doubled ('}}'); a {hole} cannot contain a brace", "error")], "a lone brace")
    eq([p[:2] for p in lint_line("  {$aa} {$b}", fields={"aa"})], [(9, 11)], "the missing $b itself")
    eq([p[:2] for p in lint_line("{$r.tagg}", loops={"r": frozenset({"tag"})})], [(1, 8)], "the whole $r.tagg")
    found = lint({"t": "x\n  @use  nope  "})
    eq([(p.where, p.start, p.end) for p in found], [(2, 8, 12)], "an @use name inside an indented line")
    found = lint({"t": "@for $i in 1..{$n}: {$i.z}"}, start="t", fields={"_db"}, tables={})
    eq(sorted((p.start, p.end) for p in found), [(15, 17), (21, 25)], "a range-end hole + an inline body hole")
    found = lint({"t": '  @for $s in signals where $s.tag = "P1"\nx\n  @end'}, start="t", fields={"_db"},
                 tables={"signals": ["tag"]})
    eq([(p.start, p.end) for p in found], [(27, 29)], "a `where` predicate's name, in an indented line")


def test_silent_literals_and_boundary_lines():
    """Two renders that SUCCEED yet likely betray the author are warnings (refuter round 17 note 1):
    the empty hole `{}` renders "" (an empty JSON object silently lost) and `{{$x}}` renders the
    literal text `{$x}` (Python's pairing - a hole in braces is `{{{$x}}}`). And the lines no branch
    walks - an @else, an @end - are grammar-checked like the renderer's block scan does."""
    found = lint_line('{} {{$x}} {{{$x}}} {{ P }}')
    eq([(s, e, severity) for s, e, _m, severity in found], [(0, 2, "warning"), (3, 9, "warning")],
       "the empty hole and the braced literal - not the braced hole, not a pragma")
    ok("{{{$x}}}" in found[1][2], f"…with the fix spelled out: {found[1][2]}")
    found = lint({"t": "@if $a\nA\n@else if $b\nB\n@end now"})
    eq(sorted(p.where for p in found if p.severity == "error"), [3, 5], "`@else if` and `@end now`")


def test_the_shipped_worked_examples_lint_clean():
    """The shipped authoring manual's worked examples: clean without a context, clean in their full
    context - and the context walk catches a field the rule's rows would lack."""
    templates = _read_yaml(_SHIPPED)
    eq(lint(templates), [], "no context")
    full = {"LineName", "BeltName", "NumPhotocells", "PecInputTag", "ConveyorPecA", "_params", "_rule", "_db"}
    eq(lint(templates, start="StandardBelt", fields=full), [], "the full context")
    found = lint(templates, start="StandardBelt", fields=full - {"PecInputTag"})
    eq([(p.template, p.where) for p in found], [("IN_Photocell", 1)], "a field missing in an @use'd leaf")


# --- the engine doors ------------------------------------------------------------------------------ #
def _database():
    src = Table("src", columns=["uid", "kind", "name"], key_columns=["name"])
    src.add(kind="door", name="D1")
    src.add(kind="motor", name="M1")
    dst = Table("dst", columns=["uid", "label", "spawned_by", "source_uid"], key_columns=["label"])
    return Database([src, dst])


def _rule(**over):
    row = {"name": "r1", "fire_when": "after_300", "source_table": "src", "condition": "",
           "action": "add_rows", "target": "dst", "template": "rows", "comment": ""}
    row.update(over)
    rules, findings = engine.compile_rules([row])
    eq(findings, [], "the rule compiles")
    return rules[0]


def _sandboxed(fn):
    original = config.database_dir
    with tempfile.TemporaryDirectory() as sandbox:
        config.database_dir = lambda: sandbox
        try:
            fn()
        finally:
            config.database_dir = original


def test_preview_equals_the_fire():
    """A preview for row i IS what a fire does for row i: the spawned rows (provenance included), the
    file path + text, the finding (type + detail) - compared against REAL fires on a fresh database."""
    def body():
        templates = {"rows": [{"label": "{{\"of\": \"{$name}\"}}"}, {"label": "two-{$name}"}],
                     "txt": "{{ P := '{$name}' }}\n@if $kind = \"door\"\nDOOR\n@end", "bad": [{"label": "{$nme}"}]}
        for index, name in enumerate(("D1", "M1")):
            database, findings = engine.fire("after_300", _database(), templates=templates, params={},
                                             rules=[_rule(condition=f'$name = "{name}"')])
            fired = [r for r in database["dst"]]
            shown = engine.preview(_rule(), index, templates=templates, params={}, database=_database())
            eq((shown.matched, shown.rows, shown.problem), (True, fired, None), f"add_rows row {index}")
            kept = _database()                               # the builder keeps the hook's layer
            eq(engine.preview(_rule(), index, templates=templates, params={}, database=kept,
                              layer=engine.db_layer(kept)), shown, "a kept layer previews the same")
        with tempfile.TemporaryDirectory() as out:
            rule = _rule(action="file", target="gen/{$name}.scl", template="txt")
            engine.fire("after_300", _database(), templates=templates, params={}, rules=[rule], files_root=out)
            for index, name in enumerate(("D1", "M1")):
                shown = engine.preview(rule, index, templates=templates, params={}, database=_database(),
                                       files_root=out)
                with open(shown.path, encoding="utf-8") as handle:
                    eq(handle.read(), shown.text + "\n", f"file row {index}: the fire wrote exactly the preview")
                eq(os.path.normcase(os.path.abspath(shown.path)),
                   os.path.normcase(os.path.join(out, "gen", f"{name}.scl")), "…at the previewed path")
        database, findings = engine.fire("after_300", _database(), templates=templates, params={},
                                         rules=[_rule(template="bad")])
        shown = engine.preview(_rule(template="bad"), 0, templates=templates, params={}, database=_database())
        eq(shown.problem, (findings[0].type, findings[0].detail), "a failing template: the fire's finding")
    _sandboxed(body)


def test_preview_states():
    """The preview's other outcomes, each what a fire would do: a condition that does not match, a
    source-less rule, a database-less hook, an empty source table, a clamped row index, a colon target."""
    templates = {"rows": [{"label": "L-{$name}"}], "txt": "hello {$_rule.name}"}
    shown = engine.preview(_rule(condition='$kind = "door"'), 1, templates=templates, params={}, database=_database())
    eq((shown.matched, shown.rows[0]["label"]), (False, "L-M1"), "not matched - still rendered, flagged")
    shown = engine.preview(_rule(source_table="", action="file", target="h.txt", template="txt"), 9,
                           templates=templates, params={}, database=None, files_root="out")
    eq((shown.matched, shown.text, shown.problem), (True, "hello r1", None), "a source-less file rule at a database-less hook")
    shown = engine.preview(_rule(fire_when="before_300"), 0, templates=templates, params={}, database=None)
    eq(shown.problem, ("rx_unknown_table", "source table 'src' is not in the database at this hook"), "no database")
    empty = Database([Table("src", columns=["uid", "kind", "name"]), Table("dst", columns=["uid", "label"])])
    shown = engine.preview(_rule(), 0, templates=templates, params={}, database=empty)
    ok(not shown.matched and "no rows" in shown.note and shown.problem is None, "an empty source table")
    eq(engine.preview(_rule(), 99, templates=templates, params={}, database=_database()).rows[0]["label"],
       "L-M1", "an out-of-range index is clamped")
    shown = engine.preview(_rule(action="file", target="X:{$name}.txt", template="txt"), 0, templates=templates,
                           params={}, database=_database(), files_root="out")
    eq(shown.problem[0], "rx_file_write", "a relative colon target is refused as the fire refuses it")


def test_engine_lint_judges_entries_and_rules():
    """The engine's lint: each entry for its KIND, a row template's values (located by entry + field),
    and - with a rule - the rule's own problems (template=None) and its E1 scope."""
    templates = {"rows": [{"label": "L-{$nme}", "desc": "{$x"}], "empty": [], "num": 7,
                 "txt": "{$name} {$kindd}"}
    found = engine.lint(templates)
    eq(sorted((p.template, str(p.where)) for p in found),
       [("empty", "None"), ("num", "None"), ("rows", "(1, 'desc')")],
       "no context: shapes + value syntax (a missing field needs a context)")
    found = engine.lint(templates, _rule(), _database(), hooks=("before_300", "after_300"))
    ok(any(p.where == (1, "label") and "$nme" in p.message for p in found), "the rule's row template in its E1 scope")
    ok(not any(p.template == "txt" and "missing" in p.message for p in found), "…not another rule's text template")
    found = engine.lint(templates, _rule(action="file", target="gen/{$nam}.txt", template="txt"), _database())
    ok(any(p.template == "txt" and "$kindd" in p.message for p in found), "a file rule's text template in scope")
    ok(any(p.template is None and p.where == "target" and "$nam" in p.message for p in found), "…and its target")
    found = engine.lint(templates, _rule(fire_when="after_900", template="txt"), None, hooks=("before_300", "after_300"))
    messages = " | ".join(p.message for p in found if p.template is None)
    for needle in ("is not a ROW template", "never fired", "source table 'src'", "target table 'dst'"):
        ok(needle in messages, f"a rule problem: {needle!r} ({messages})")
    found = engine.lint({"own": [{"label": "L-{$name}"}]}, _rule(template="own"), None)
    eq([p.message for p in found if p.template == "own"], [],
       "an absent source table does not flood the rule's own holes as missing (one rule problem says why)")
    ok(any("source table 'src'" in p.message for p in found), "…the rule problem")
    colon = engine.lint({"txt": "x"}, _rule(action="file", target="gen/a:{$name}.txt", template="txt"), _database())
    eq([(p.where, p.start) for p in colon if p.template is None], [("target", 5)],
       "a literal ':' in a target - the fire refuses every row (C-025 round 1)")
    drive = engine.lint({"txt": "x"}, _rule(action="file", target="C:/out/{$name}.txt", template="txt"), _database())
    eq([p for p in drive if p.template is None], [], "…a drive's colon is fine")
    colon = engine.lint({"txt": "x"}, _rule(action="file", target="{$name}:x/{$name}.txt", template="txt"), _database())
    eq([(p.where, p.start) for p in colon if p.template is None], [("target", 7)], "…a hole's colon without a separator")

    def drive_from_a_hole():                                  # C-024 refute round 19's note: the lint called a
        with tempfile.TemporaryDirectory() as out:           # drive a HOLE renders a refused colon
            letter, rest = os.path.splitdrive(out)
            if not letter:
                return                                        # (no drive letters on this platform)
            target = "{$_params.drv}:" + rest.replace("\\", "/") + "/{$name}.txt"
            rule = _rule(action="file", target=target, template="txt")
            eq([p for p in engine.lint({"txt": "x"}, rule, _database()) if p.template is None], [],
               "a drive a hole renders is the fire's to judge - no lint error")
            _, findings = engine.fire("after_300", _database(), rules=[rule], templates={"txt": "x"},
                                      params={"drv": letter[0]}, files_root=out)
            eq((findings, sorted(os.listdir(out))), ([], ["D1.txt", "M1.txt"]), "…and the fire writes it")
    _sandboxed(drive_from_a_hole)


def test_format_specs_are_judged_in_every_branch():
    """C-025 refute round 1: a hole's format spec was never checked - a typo in an untaken branch
    linted clean, previewed fine, and failed the fire the day a row took the branch. A spec no value
    can satisfy is an error; one some value satisfies (by its type letter) is not."""
    body = '@if $kind = "motor"\nMOTOR {$name:03D}\n@else\nDOOR {$name}\n@end'
    found = lint({"t": body}, start="t", fields={"kind", "name", "_params", "_rule", "_db"})
    eq([(p.where, p.severity) for p in found], [(2, "error")], "the untaken branch's bad spec")
    ok("'03D'" in found[0].message, found[0].message)
    eq(lint_line("{$n:,.2f} {$i:03} {$n:+} {$x:>8} {$d:x}"), [], "specs some value satisfies")
    rule = _rule(action="file", target="m.txt", template="t")

    def fired():
        with tempfile.TemporaryDirectory() as out:
            _, findings = engine.fire("after_300", _database(), rules=[rule], templates={"t": body}, params={},
                                      files_root=out)
            eq([x.type for x in findings], ["rx_bad_template"], "the fire rejects it once a motor row comes")
            ok("03D" in findings[0].detail, findings[0].detail)
    _sandboxed(fired)


def test_use_depth_is_judged_whatever_the_order():
    """C-025 refute round 1: the no-context walk sees each template once, so a 34-deep @use chain
    listed leaf-first linted clean while its render stops at the nesting limit."""
    chain = {f"t{i}": f"@use t{i + 1}" for i in range(33)}
    chain["t33"] = "leaf"
    for order in (chain, dict(reversed(list(chain.items())))):
        ok(any(p.template == "t0" and "deeper than" in p.message for p in lint(order)), "in either order")
    try:
        render_template("t0", chain, {})
        ok(False, "the render must stop")
    except TempemplatorError as error:
        ok("deeper than" in error.message, error.message)
    short = {f"t{i}": f"@use t{i + 1}" for i in range(20)}
    short["t20"] = "leaf"
    eq(lint(short), [], "a chain within the limit")


def test_preview_keeps_the_fires_guards():
    """C-025 refute round 1: the preview skipped the fire's own guards - a hook the run-plan never
    fires previewed normally, and an unforeseen exception RAISED out of it (the view died). Both are
    the fire's findings now; a `self` field previews as the fire spawns it."""
    templates = {"rows": [{"label": "L-{$name}", "self": "me"}], "txt": "hello {$name}"}
    shown = engine.preview(_rule(fire_when="after_900", action="file", target="h.txt", template="txt"), 0,
                           templates=templates, params={}, database=_database(), files_root="o",
                           hooks=("before_300", "after_300"))
    eq((shown.matched, shown.problem[0]), (None, "rx_unfired_hook"), "a hook never fired")
    real = engine.tempemplator.render_text

    def boom(text, ctx):
        raise RuntimeError("boom")

    def body():
        engine.tempemplator.render_text = boom
        try:
            _, findings = engine.fire("after_300", _database(), rules=[_rule()], templates=templates, params={})
            shown = engine.preview(_rule(), 0, templates=templates, params={}, database=_database())
        finally:
            engine.tempemplator.render_text = real
        eq(shown.problem, (findings[0].type, findings[0].detail), "the backstop: exactly the fire's rx_rule_crashed")
        eq(shown.matched, True, "…for a row the condition matches")
        real_test = engine.expr.test

        def broken_test(*_args, **_kwargs):
            raise RuntimeError("condition defect")

        engine.expr.test = broken_test                  # a crash BEFORE the condition says anything
        try:
            shown = engine.preview(_rule(condition='$kind = "door"'), 0, templates=templates, params={},
                                   database=_database())
        finally:
            engine.expr.test = real_test
        eq((shown.matched, shown.problem[0]), (None, "rx_rule_crashed"), "matched stays None - never a false 'no match'")
        database, findings = engine.fire("after_300", _database(), rules=[_rule()], templates=templates, params={})
        eq(findings, [], "a `self` field fires")
        for index, fired in enumerate(database["dst"]):
            eq(engine.preview(_rule(), index, templates=templates, params={}, database=_database()).rows, [fired],
               f"a `self` field: row {index} previews as the fire spawns it")
    _sandboxed(body)


def test_has_business_mirrors_the_fires_no_op():
    """`has_business` answers exactly `fire`'s strict no-op test - the builder's model of a settled
    database-less hook depends on it: a rule on the hook, or a rule-INDEX problem (every hook's)."""
    row = {"name": "h", "fire_when": "before_300", "source_table": "", "condition": "", "action": "file",
           "target": "x.txt", "template": "t"}
    hooks = ("before_300", "after_300")
    eq(engine.has_business("before_300", [row], hooks), True, "a rule on the hook")
    eq(engine.has_business("before_300", [], hooks), False, "nothing: the strict no-op")
    eq(engine.has_business("before_300", [{**row, "fire_when": "after_300"}], hooks), False, "another hook's rule")
    eq(engine.has_business("before_300", [{**row, "fire_when": "whenever"}], hooks), True,
       "a row naming no hook - an index problem, every hook's business")
    eq(engine.has_business("before_300", [{**row, "fire_when": "after_900"}], hooks), True,
       "a rule on a hook the run-plan never fires - every hook's business")
    eq(engine.has_business("before_300", [{**row, "name": ""}], hooks), True, "its own malformed rule")
    for rows in ([row], [], [{**row, "fire_when": "after_300"}], [{**row, "fire_when": "whenever"}]):
        with tempfile.TemporaryDirectory() as out:
            deferred, _findings = engine.fire("before_300", None, rules=rows, templates={"t": "x"}, params={},
                                              files_root=out, hooks=hooks)
        eq(deferred is not None, engine.has_business("before_300", rows, hooks), f"the fire agrees: {rows}")


def test_preview_sees_the_in_hook_cascade():
    """C-025 refute round 1: a later rule of a hook SEES an earlier rule's spawns (the chain reaction
    within one hook) - the preview did not. `cascade` runs the earlier add_rows rules through the
    fire's own step on a copy; the preview over it equals the real multi-rule fire."""
    rules, findings = engine.compile_rules([
        {"name": "A", "fire_when": "after_300", "source_table": "src", "condition": "", "action": "add_rows",
         "target": "dst", "template": "rows"},
        {"name": "B", "fire_when": "after_300", "source_table": "dst", "condition": "", "action": "file",
         "target": "{$label}.txt", "template": "each"},
        {"name": "C", "fire_when": "after_300", "source_table": "", "condition": "", "action": "file",
         "target": "count.txt", "template": "count"}])
    eq(findings, [], "the rules compile")
    templates = {"rows": [{"label": "L-{$name}"}], "each": "row {$label}", "count": "dst has {count(dst)} rows"}

    def body():
        with tempfile.TemporaryDirectory() as out:
            engine.fire("after_300", _database(), rules=rules, templates=templates, params={}, files_root=out)
            fired = {name: open(os.path.join(out, name), encoding="utf-8").read() for name in os.listdir(out)}
            base = _database()
            for index, name in enumerate(("L-D1.txt", "L-M1.txt")):
                seen, _problems = engine.cascade(rules, rules[1], base, templates=templates, params={})
                shown = engine.preview(rules[1], index, templates=templates, params={}, database=seen, files_root=out)
                eq((os.path.basename(shown.path), shown.text + "\n"), (name, fired[name]), f"B row {index}")
            seen, _problems = engine.cascade(rules, rules[2], base, templates=templates, params={})
            shown = engine.preview(rules[2], 0, templates=templates, params={}, database=seen, files_root=out)
            eq(shown.text + "\n", fired["count.txt"], "C counts A's spawns")
            eq(len(base["dst"]), 0, "the cascade spawned into a COPY - the hook's Database is untouched")
            alone = engine.preview(rules[1], 0, templates=templates, params={}, database=base, files_root=out)
            ok("no rows" in alone.note, "(without the cascade B saw an empty dst - the round-1 finding)")
    _sandboxed(body)


def test_windows_refused_target_characters():
    """C-025 refute round 2 (#4): a literal character a Windows path refuses (`<>"|?*`, a control
    character) in a file target linted clean and previewed fine, while the fire refused every row
    (EINVAL at open). The lint, the preview and the fire name the same refusal now - and a character
    a ROW renders is data: the fire's (and that row's preview's) to judge, never the lint's."""
    if os.name != "nt":
        return                                                # other platforms accept these characters
    templates = {"txt": "x"}

    def body():
        for target in ('"rx/out.txt"', "rx/report?.txt", "rx/a|b.txt", "rx/<x>.txt", "rx/all*.txt", "rx/a\tb.txt"):
            rule = _rule(action="file", target=target, template="txt")
            found = [p for p in engine.lint(templates, rule, _database()) if p.template is None]
            eq([(p.where, p.severity) for p in found], [("target", "error")], f"{target!r}: the lint")
            eq(target[found[0].start], [c for c in target if c in '"|?*<>\t'][0], f"{target!r}: on the character")
            with tempfile.TemporaryDirectory() as out:
                _, findings = engine.fire("after_300", _database(), rules=[rule], templates=templates, params={},
                                          files_root=out)
                shown = engine.preview(rule, 0, templates=templates, params={}, database=_database(), files_root=out)
                eq([f.type for f in findings], ["rx_file_write"], f"{target!r}: the fire refuses it")
                ok("is not allowed in a Windows path" in findings[0].detail, findings[0].detail)
                eq(shown.problem, (findings[0].type, findings[0].detail), f"{target!r}: the preview says the fire's finding")
                eq(os.listdir(out), [], "…and nothing is written")
        rule = _rule(action="file", target="rx/{$name}.txt", template="txt")
        eq([p for p in engine.lint(templates, rule, _database()) if p.template is None], [], "a hole is data - no lint error")
        database = _database()
        database["src"].add(kind="valve", name="V?1")
        with tempfile.TemporaryDirectory() as out:
            _, findings = engine.fire("after_300", database, rules=[rule], templates=templates, params={}, files_root=out)
            eq([f.type for f in findings], ["rx_file_write"], "the row rendering '?' is refused")
            shown = engine.preview(rule, 2, templates=templates, params={}, database=database, files_root=out)
            eq(shown.problem, (findings[0].type, findings[0].detail), "…and that row's preview says so")
            eq(engine.preview(rule, 0, templates=templates, params={}, database=database, files_root=out).problem,
               None, "…another row previews clean")
    _sandboxed(body)


def test_drive_targets_are_the_fires_to_judge():
    """C-025 refute round 3 (F2, F3): a literal drive followed by a HOLE (`C:{$_params.dir}/x.txt`) and an
    extended-length `\\\\?\\C:\\...` target linted as refused while the fire writes both - the builder
    rejected what the fire accepts. The lint skips a drive's own characters and leaves a drive a hole
    completes to the fire, row by row; a drive-relative literal (`X:1.txt`) is still refused."""
    if os.name != "nt":
        return                                                # no drive letters elsewhere
    templates = {"txt": "x"}

    def body():
        with tempfile.TemporaryDirectory() as out:
            drive, rest = os.path.splitdrive(out)
            params = {"dir": rest.replace("\\", "/"), "drive": drive[0], "rel": "out/x.txt"}
            for target in (drive[0] + ":{$_params.dir}/x1.txt", "{$_params.drive}:{$_params.dir}/x2.txt",
                           "\\\\?\\" + out + "\\ext.txt"):
                rule = _rule(action="file", target=target, template="txt")
                eq([p.message for p in engine.lint(templates, rule, _database()) if p.template is None], [],
                   f"{target!r}: no lint error")
                shown = engine.preview(rule, 0, templates=templates, params=params, database=_database(), files_root=out)
                _, findings = engine.fire("after_300", _database(), rules=[rule], templates=templates, params=params,
                                          files_root=out)
                eq((shown.problem, findings), (None, []), f"{target!r}: the preview and the fire accept it")
            eq(sorted(os.listdir(out)), ["ext.txt", "x1.txt", "x2.txt"], "…the fire wrote each")
            rule = _rule(action="file", target=drive[0] + ":{$_params.rel}", template="txt")
            eq([p for p in engine.lint(templates, rule, _database()) if p.template is None], [],
               "a drive a hole completes: the fire's to judge")
            shown = engine.preview(rule, 0, templates=templates, params=params, database=_database(), files_root=out)
            _, findings = engine.fire("after_300", _database(), rules=[rule], templates=templates, params=params,
                                      files_root=out)
            eq(shown.problem, (findings[0].type, findings[0].detail),
               "…a row it renders drive-relative is refused by the fire, and its preview says so")
            flagged = engine.lint(templates, _rule(action="file", target="X:1.txt", template="txt"), _database())
            eq([(p.where, p.start) for p in flagged if p.template is None], [("target", 1)],
               "a drive-relative literal is still refused")
    _sandboxed(body)


def test_every_target_shape_lint_equals_the_fire():
    """C-025 refute round 4 (F1): the round-3 drive skip took ANY character before a ':' for a drive -
    `?:`, `1:`, `_:`, `é:`, and an extended `\\\\?\\C:` whatever followed - the lint and the preview
    approved targets the OS refuses; and two hole-driven drives were refused while the fire writes them.
    A drive is at most ONE ASCII letter (plus holes that may render it) now, the fire refuses a
    non-letter drive and an extended drive-relative path before the write - lint = preview = fire."""
    if os.name != "nt":
        return                                                # drive letters: Windows only
    templates = {"txt": "x"}

    def body():
        with tempfile.TemporaryDirectory() as out:
            drive, rest = os.path.splitdrive(out)
            params = {"dir": rest.replace("\\", "/"), "d": "", "e": drive[0], "p": ""}
            for target in (":/rx/x.txt", "?:/rx/x.txt", "*:/rx/x.txt", "1:/rx/x.txt", "1:\\rx\\x.txt", "_:\\rx\\x.txt",
                           "\u00e9:\\rx\\x.txt", "1:{$_params.dir}/e.txt", "\\\\?\\" + drive[0] + ":i.txt",
                           "\\\\srv\\sh?re\\x.txt"):             # (a share's '?': refused BEFORE any network)
                rule = _rule(action="file", target=target, template="txt")
                lint_errors = [p for p in engine.lint(templates, rule, _database()) if p.template is None]
                shown = engine.preview(rule, 0, templates=templates, params=params, database=_database(), files_root=out)
                _, findings = engine.fire("after_300", _database(), rules=[rule], templates=templates, params=params,
                                          files_root=out)
                eq([f.type for f in findings], ["rx_file_write"], f"{target!r}: the fire refuses it")
                eq(shown.problem, (findings[0].type, findings[0].detail), f"{target!r}: …the preview says so")
                eq([p.severity for p in lint_errors], ["error"], f"{target!r}: …and so does the lint")
            for target in ("{$_params.d}{$_params.e}:{$_params.dir}/two_holes.txt",
                           "{$_params.p}" + drive[0] + ":{$_params.dir}/hole_then_letter.txt"):
                rule = _rule(action="file", target=target, template="txt")
                eq([p.message for p in engine.lint(templates, rule, _database()) if p.template is None], [],
                   f"{target!r}: a drive the holes render - no lint error")
                _, findings = engine.fire("after_300", _database(), rules=[rule], templates=templates, params=params,
                                          files_root=out)
                eq(findings, [], f"{target!r}: …the fire writes it")
            eq(sorted(os.listdir(out)), ["hole_then_letter.txt", "two_holes.txt"], "…both written")
    _sandboxed(body)


def test_a_data_functions_row_reads_are_judged():
    """C-025 refute round 2 (#5): a data function reads ITS table's rows - a predicate's `$col`,
    lookup's / unique's column words - and a column the table does not have reads BLANK (count() then
    counts nothing, silently). The lint warns there now, in text templates and row values alike; a
    real column is clean."""
    from pipeline5.language import expr
    tables = {"signals": ["uid", "mnemonic", "script_type"], "diagnosis_cabinets": ["cabinet_id", "fld"]}
    fields = {"cabinet_id", "fld", "_params", "_rule", "_db"}
    body = ('{count(signals, $cabinet_id = "C1")} {count(signals, $script_type = "A")}\n'
            '{first(signals, $colour = "red")} {where(signals, $mnemonic = "M")}\n'
            '{lookup(signals, mnemonic, "M1", colour)} {unique(tag, signals)}')
    found = lint({"t": body}, start="t", fields=fields, tables=tables)
    eq(sorted((p.where, body.split("\n")[p.where - 1][p.start:p.end], p.severity) for p in found),
       [(1, "$cabinet_id", "warning"), (2, "$colour", "warning"), (3, "colour", "warning"), (3, "tag", "warning")],
       "each unknown row read, located - warnings (a blank read, not a render error)")
    ok("'cabinet_id' is not a column of signals - count() reads it as blank" in found[0].message, found[0].message)
    found = lint({"t": '@for $s in signals where count(diagnosis_cabinets, $colour = "x") > 0: {$s.uid}\n'
                       '@for $i in 1..{count(signals, $nope = 1)}: x'}, start="t", fields=fields, tables=tables)
    eq(sorted((p.where, p.severity, p.message.split(" - ")[0]) for p in found),
       [(1, "warning", "count() inside a row predicate sees that ROW alone"),
        (2, "warning", "'nope' is not a column of signals")],
       "…a range end's too; inside a `where` a data function sees the ROW alone - it finds no rows at all "
       "(C-025 refute round 4, F2)")
    ctx = {"cabinet_id": "C1", "_db": {"signals": [{"uid": "u", "mnemonic": "M", "script_type": "A"}]}}
    eq(expr.evaluate('count(signals, $cabinet_id = "C1")', ctx), 0.0, "(what the fire computes: nothing matches)")
    body = '{count(signalz, $script_type = "PEC")} {lookup(signalz, tag, "P1", script_type)} {count(signalz)}'
    found = lint({"t": body}, start="t", fields=fields, tables=tables)
    eq(sorted((p.start, p.severity) for p in found),
       [(body.index("signalz", body.index(hole)), "warning") for hole in ("{count(signalz, $", "{lookup(", "{count(signalz)}")],
       "a table the hook does not have - each function over it, warned (C-025 refute round 3, F5)")
    ok(all("'signalz' is not a table at this hook" in p.message for p in found), [p.message for p in found])
    eq((expr.evaluate('count(signalz, $script_type = "PEC")', ctx), expr.evaluate("count(signalz)", ctx)), (0.0, 0.0),
       "(what the fire computes: nothing, silently)")
    before = _rule(fire_when="before_300", source_table="", action="file", target="b.txt", template="b")
    found = engine.lint({"b": '@for $r in signals: x\nsignals: {count(signals)} first: {lookup(signals, tag, "P1", uid)}\n'
                              '@if count(signals) > 0\ny\n@end'}, before, None, hooks=("before_300", "after_300"))
    eq(sorted((p.where, p.severity) for p in found if p.template == "b"),
       [(1, "error"), (2, "warning"), (2, "warning"), (3, "warning")],
       "a database-less hook: no table at all - the @for's error, each data function warned (round 4, F2)")
    found = lint({"t": '@for $r in signals where count(signals) > 0: {$r.uid}\n{count(signals, count(signals) > 0)}'},
                 start="t", fields=fields, tables=tables)
    eq(sorted((p.where, p.message.split(" - ")[0]) for p in found),
       [(1, "count() inside a row predicate sees that ROW alone"), (2, "count() inside a row predicate sees that ROW alone")],
       "a data function inside a ROW predicate finds no rows - warned, on the function")
    ok(expr.evaluate("count(signals, count(signals) > 0)", {"_db": {"signals": [{"uid": "u"}]}}) == 0.0,
       "(what the fire computes: nothing)")
    database = _database()
    database.add_table(Table("signals", columns=tables["signals"]))
    rows = engine.lint({"rows": [{"n": '{count(signals, $cabinet_id = "C1")}'}]}, _rule(), database)
    ok(any(p.where == (1, "n") and "cabinet_id" in p.message and p.severity == "warning" for p in rows),
       f"…in a row template's value too ({rows})")


def test_a_lone_surrogate_is_what_the_fire_refuses():
    """C-024 refute round 21's builder half: text UTF-8 cannot store (a YAML `\\uD83D\\uDE00` pair decodes to
    two lone surrogates) - the fire refuses every row now; the lint says so (an error on the character)
    in a text template and a row value, the preview gives the fire's finding - and a file TARGET holding
    one is left alone (a path is not stored as UTF-8)."""
    lone = "\ud83d\ude00"
    templates = {"rows": [{"label": "E" + lone}], "txt": "smile " + lone}
    found = engine.lint(templates, _rule(), _database())
    eq(sorted((p.template, str(p.where), p.severity) for p in found if "surrogate" in p.message),
       [("rows", "(1, 'label')", "error"), ("txt", "1", "error")], "a row value and a text line: errors")

    def body():                                               # (the fire saves its record: sandboxed)
        _database_, findings = engine.fire("after_300", _database(), rules=[_rule()], templates=templates, params={})
        shown = engine.preview(_rule(), 0, templates=templates, params={}, database=_database())
        eq(shown.problem, (findings[0].type, findings[0].detail), "the preview is the fire's rx_bad_template")
    _sandboxed(body)
    target = [p for p in engine.lint({"txt": "x"}, _rule(action="file", target="o" + lone + ".txt", template="txt"),
                                     _database()) if "surrogate" in p.message]
    eq(target, [], "a target is not stored as UTF-8 - no error there")


def test_format_specs_know_the_values_type():
    """C-025 refute round 2 (#9): `{$j:>5}` on a JSON (list) column linted clean yet fails every
    non-blank row (a list takes no format spec), and `{count(t):,.1}` was an error yet renders
    (count() returns a float). A JSON value's spec warns now - the rule's own and a loop row's - and
    a spec some float satisfies is accepted."""
    from pipeline5.language.tempemplator import render_text
    tables = {"t": ["uid", "a", "j"]}
    body = "{$j:>5} {$a:>5}\n@for $r in t: {$r.j:>4} {$r.a:>4}"
    found = lint({"m": body}, start="m", fields={"a", "j", "_params", "_rule", "_db"}, tables=tables,
                 json={"t": frozenset({"j"})}, json_fields=frozenset({"j"}))
    eq(sorted((p.where, p.severity) for p in found), [(1, "warning"), (2, "warning")], "the two JSON values")
    ok(all("JSON" in p.message for p in found), [p.message for p in found])
    eq(lint_line("{count(t):,.1} {count(t):03d}"), [], "specs a float / an int satisfies")
    eq(render_text("{count(t):,.1}", {"_db": {"t": [{}, {}]}}), "2e+00", "(it renders)")
    database = Database([Table("src", columns=["uid", "kind", "name", "j", "im"], json_columns=["j", "im"],
                               key_columns=["name"]),
                         Table("dst", columns=["uid", "label"])])
    database["src"].add(kind="door", name="D1", j=[1, 2], im="01|02")
    rule = _rule(action="file", target="o.txt", template="m")
    found = engine.lint({"m": "{$j:>5}"}, rule, database)
    ok(any(p.template == "m" and p.severity == "warning" and "JSON" in p.message for p in found),
       f"the engine carries the rule's JSON columns ({found})")
    eq([p for p in engine.lint({"m": "{$j:}"}, rule, database) if p.template == "m"], [],
       "an EMPTY spec formats a list fine - no warning (round 4, F6)")
    eq([p for p in engine.lint({"m": "{$im:>8}"}, rule, database) if p.template == "m"], [],
       "a declared JSON column that HOLDS text is text (C-025 refute round 3, F4 - a staged I/O-List cell)")
    with tempfile.TemporaryDirectory() as out:
        shown = engine.preview(_rule(action="file", target="o.txt", template="m"), 0, templates={"m": "{$im:>8}"},
                               params={}, database=database, files_root=out)
        eq((shown.problem, shown.text), (None, "   01|02"), "…and it renders")

    def fired():
        with tempfile.TemporaryDirectory() as out:
            _, findings = engine.fire("after_300", database, rules=[rule], templates={"m": "{$j:>5}"}, params={},
                                      files_root=out)
            eq([f.type for f in findings], ["rx_bad_template"], "the fire fails on the non-blank row")
    _sandboxed(fired)


def test_a_field_name_utf8_cannot_store_is_the_templates_error():
    """C-025 refute round 5 (#1): the round-4 surrogate lint judged a row template's VALUES only - a FIELD NAME
    holding the pair (`"tag\\uD83D\\uDE00": ...`, a YAML key) linted clean and previewed a spawn, while the real
    run added the row and its save emptied signals.csv (C-024 round 22, F-B). The field name is the row
    template's own problem now - one check (`_row_template_problem`) for the lint, the preview and the fire."""
    pair = "\ud83d\ude00"
    templates = {"rows": [{"label": "ok-{$name}", "tag" + pair: "x"}]}
    found = [p for p in engine.lint(templates, _rule(), _database()) if p.severity == "error"]
    eq([(p.template, p.where) for p in found], [(None, None), ("rows", None)], "the rule's error and the template's")
    ok(all("entry 1: the field name 'tag\\ud83d\\ude00'" in p.message for p in found), [p.message for p in found])

    def body():
        database, findings = engine.fire("after_300", _database(), rules=[_rule()], templates=templates, params={})
        shown = engine.preview(_rule(), 0, templates=templates, params={}, database=_database())
        eq(shown.problem, (findings[0].type, findings[0].detail), "the preview is the fire's rx_bad_template")
        eq((shown.rows, len(database["dst"])), ([], 0), "…nothing spawned, nothing added")
    _sandboxed(body)


def test_device_prefixes_and_names_lint_equals_the_fire():
    """C-025 refute round 5 (#2, #5) + C-024 refute round 22's notes, the builder half: the lint approved exact
    `\\\\?\\` targets every fire refuses (a '/', a '.' / '..' name), and rejected device-prefix spellings the
    fire writes (`\\\\./C:`, `//.\\C:`, `\\/.\\C:`, `//?/C:` or `\\\\.\\C:` after a leading hole). The fire's new
    name guards (a device name, a name ending in '.' / ' ', a rooted path, no file name, a device path's
    volume) are the lint's too, on literal text: lint = preview = fire for every shape - a literal is refused
    only where no rendering of the holes lets the fire take it."""
    if os.name != "nt":
        return                                                # Win32 path rules
    templates = {"txt": "x"}

    def body():
        with tempfile.TemporaryDirectory() as out:
            drive, rest = os.path.splitdrive(out)
            letter, strict = drive[0], "\\\\?\\" + out
            params = {"dir": rest.replace("\\", "/"), "p": "", "n": "", "a": "a", "e": "txt", "v": "v"}
            rooted = f"/rx_rooted_{os.getpid()}/a.txt"            # unique: were its refusal lost, the join lands it at
            landed = os.path.join(drive + os.sep, rooted[1:])     # the drive's ROOT - removed below
            refused = [strict + "/lit.txt", strict + "\\sub/b.txt", strict + "\\sub\\..\\c.txt", strict + "\\.\\d.txt",
                       strict + "\\\\e.txt", "{$_params.p}\\\\?\\" + letter + ":{$_params.dir}/a.txt",
                       "\\\\.\\" + letter + ":\\..\\" + rest.lstrip("\\") + "\\x.txt", "\\\\.\\pipe\\rx", "rx/NUL",
                       "rx/nul.{$_params.e}", "rx/a.", "rx /a.txt", rooted, "rx/", "rx/{$_params.v}.",
                       "rx/{$_params.v} /x.txt"]
            try:
                for target in refused:
                    rule = _rule(action="file", target=target, template="txt")
                    errors = [p for p in engine.lint(templates, rule, _database())
                              if p.template is None and p.severity == "error"]
                    shown = engine.preview(rule, 0, templates=templates, params=params, database=_database(),
                                           files_root=out)
                    _, findings = engine.fire("after_300", _database(), rules=[rule], templates=templates,
                                              params=params, files_root=out)
                    eq([f.type for f in findings], ["rx_file_write"], f"{target!r}: the fire refuses it")
                    eq(shown.problem, (findings[0].type, findings[0].detail), f"{target!r}: …the preview says so")
                    eq([p.where for p in errors], ["target"], f"{target!r}: …and so does the lint")
            finally:
                if os.path.isfile(landed):
                    os.remove(landed)
                    os.rmdir(os.path.dirname(landed))
            eq(os.listdir(out), [], "nothing written")
            accepted = {"{$_params.p}//?/" + letter + ":{$_params.dir}/b.txt": "b.txt",
                        "{$_params.p}\\\\.\\" + letter + ":{$_params.dir}/c.txt": "c.txt",
                        "\\\\./" + letter + ":{$_params.dir}/d.txt": "d.txt",
                        "//.\\" + letter + ":{$_params.dir}/e.txt": "e.txt",
                        "\\/.\\" + letter + ":{$_params.dir}/f.txt": "f.txt",
                        "//?/" + out.replace("\\", "/") + "/sub/../g.txt": "g.txt",
                        "rx/{$_params.n}./h.txt": os.path.join("rx", "h.txt"),
                        "rx/NUL{$_params.a}.txt": os.path.join("rx", "NULa.txt")}
            for target, name in accepted.items():
                rule = _rule(action="file", target=target, template="txt")
                eq([p.message for p in engine.lint(templates, rule, _database()) if p.template is None], [],
                   f"{target!r}: no lint error")
                shown = engine.preview(rule, 0, templates=templates, params=params, database=_database(), files_root=out)
                _, findings = engine.fire("after_300", _database(), rules=[rule], templates=templates, params=params,
                                          files_root=out)
                eq((shown.problem, findings), (None, []), f"{target!r}: the preview and the fire accept it")
                ok(os.path.isfile(os.path.join(out, name)), f"{target!r}: …written as {name}")
    _sandboxed(body)


def test_node_of_reads_are_judged_as_every_data_functions():
    """C-025 refute round 5 (#3): node_of is a data function - listed, documented, offered by the completion -
    yet the parser never recorded its read: over a table absent at the hook (a database-less hook has none),
    inside a ROW predicate, and over a table lacking its byte-range columns it linted clean while finding
    nothing. It is judged as count / lookup are now - warnings, each on its own call or table word."""
    from pipeline5.language import expr
    tables = {"signals": ["uid", "tag"], "nodes": ["uid", "name", "start_byte", "end_byte"], "bare": ["uid", "name"]}
    body = ('{node_of($_params.bit, nodez)}\n{count(signals, node_of(1, nodes) = "")}\n'
            '{node_of($_params.bit, bare)}\n{node_of($_params.bit, nodes)}')
    found = lint({"t": body}, start="t", fields={"_params", "_rule", "_db", "tag"}, tables=tables)
    eq(sorted((p.where, body.split("\n")[p.where - 1][p.start:p.end], p.severity, p.message.split(" - ")[0])
              for p in found),
       [(1, "nodez", "warning", "'nodez' is not a table at this hook"),
        (2, "node_of", "warning", "node_of() inside a row predicate sees that ROW alone"),
        (3, "node_of", "warning", "'end_byte' is not a column of bare"),
        (3, "node_of", "warning", "'start_byte' is not a column of bare")],
       "each read the fire makes blind - warned (the real one clean)")
    ctx = {"_params": {"bit": 12}, "_db": {"nodes": [{"uid": "u", "name": "N1", "start_byte": "10", "end_byte": "20"}],
                                           "bare": [{"uid": "u", "name": "B"}]}}
    eq((expr.evaluate("node_of($_params.bit, bare)", ctx), expr.evaluate("node_of($_params.bit, nodes)", ctx)["name"]),
       ({}, "N1"), "(what the fire computes: nothing over the bare table, the node over the real one)")
    before = _rule(fire_when="before_300", source_table="", action="file", target="b.txt", template="b")
    found = engine.lint({"b": "{node_of(1, nodes)}"}, before, None, hooks=("before_300", "after_300"))
    eq([(p.template, p.severity, p.message.split(" - ")[0]) for p in found],
       [("b", "warning", "'nodes' is not a table at this hook")], "a database-less hook: no table at all")


def test_a_lone_surrogate_is_judged_where_it_is_stored():
    """C-025 refute round 5 (#4): the round-4 check scanned the WHOLE line - holes included - and stopped
    there: a compared literal (`{count(src, $name = "<pair>")}`, a row value's `{if($name = "<pair>", ...)}`)
    and a range end's `{len("<pair>")}` were errors while the fire writes them, and `{$nope} <pair>` hid the
    fire's own error (a missing field). The surrogate is judged where the render STORES it now - literal
    text and a constant hole's value an error, a data-dependent hole a warning (a row rendering it is
    refused), a predicate or a range end never - and the line's other problems still show."""
    pair = "\ud83d\ude00"

    def body():
        with tempfile.TemporaryDirectory() as out:
            for name, text, severity, written in (
                    ("a", 'matches: {count(src, $name = "' + pair + '")}', "warning", "matches: 0.0"),
                    ("c", '@for $i in 1..{count(src, $name != "' + pair + '")}: line {$i}', None, "line 1\nline 2"),
                    ("k", 'x {"' + pair + '"}', "error", None)):
                rule = _rule(action="file", source_table="", target=f"{name}.txt", template=name)
                found = [p for p in engine.lint({name: text}, rule, _database()) if "surrogate" in p.message]
                eq([p.severity for p in found], [severity] if severity else [], f"{name}: the lint")
                _, findings = engine.fire("after_300", _database(), rules=[rule], templates={name: text}, params={},
                                          files_root=out)
                if written is None:
                    eq([f.type for f in findings], ["rx_bad_template"], f"{name}: the fire refuses every row")
                    continue
                eq(findings, [], f"{name}: the fire writes it")
                with open(os.path.join(out, f"{name}.txt"), encoding="utf-8") as handle:
                    eq(handle.read().rstrip("\n"), written, f"{name}: …this")
            rows = {"rows": [{"label": '{if($name = "' + pair + '", "smile", "plain")}'}]}
            eq([p.severity for p in engine.lint(rows, _rule(), _database()) if "surrogate" in p.message], ["warning"],
               "a row value's data-dependent hole: a warning")
            database, findings = engine.fire("after_300", _database(), rules=[_rule()], templates=rows, params={})
            eq((findings, [row["label"] for row in database["dst"]]), ([], ["plain", "plain"]), "…the fire spawns it")
            rule = _rule(action="file", source_table="", target="n.txt", template="n")
            found = engine.lint({"n": "{$nope} " + pair}, rule, _database())
            eq(sorted((p.severity, p.message.split(" - ")[0]) for p in found if p.template == "n"),
               [("error", "'\\ud83d' (a lone surrogate) cannot be stored as UTF-8"), ("error", "missing field $nope")],
               "both of the line's problems - the fire's own error included")
    _sandboxed(body)


def test_an_in_row_warning_lands_on_its_own_call():
    """C-025 refute round 5 (#7): the in-row warning searched its function's NAME after the hole's first
    comma - `{lookup(signals, tag, count(nodes, count(signals) > 0), addr)}` squiggled the lookup KEY's
    `count` (column 22), not the one inside count's predicate (35); inside a `where` three calls collapsed
    into one warning. The parser records each call's own position; each warning is placed there."""
    tables = {"signals": ["uid", "tag", "addr"], "nodes": ["uid", "name"]}
    fields = {"_params", "_rule", "_db", "tag"}
    line = "{lookup(signals, tag, count(nodes, count(signals) > 0), addr)}"
    found = [p for p in lint({"t": line}, start="t", fields=fields, tables=tables) if "row predicate" in p.message]
    eq([(p.start, p.end) for p in found], [(35, 40)], "on the call inside the predicate")
    line = "@for $r in signals where count(nodes) > 0 and count(signals, count(nodes) > 0) > 0: {$r.tag}"
    found = [p for p in lint({"t": line}, start="t", fields=fields, tables=tables) if "row predicate" in p.message]
    eq(sorted((p.start, line[p.start:p.end]) for p in found), [(25, "count"), (46, "count"), (61, "count")],
       "every call inside the `where`, each on its own")


def test_a_colon_is_judged_as_written():
    """C-025 refute round 6 (#2): the fire read a ':' on the NORMALIZED path (`abspath`) - `<tmp>\\a:b\\..\\x.txt` has
    none there, so the fire wrote `<tmp>\\x.txt` while the lint refused the literal ':'; a ':' in a UNC server or
    share name sat in splitdrive's DRIVE part, unseen (and `NUL:` normalized to the device - C-024 round 23, F1). One
    rule for both now: a ':' in any name past the drive, as written - lint = preview = fire."""
    if os.name != "nt":
        return                                                # Win32 path rules
    templates = {"txt": "x"}

    def body():
        with tempfile.TemporaryDirectory() as out:
            slashed = out.replace("\\", "/")
            for target in (out + "\\a:b\\..\\x.txt", "//./" + slashed + "/c:d/../y.txt", out + "\\sub\\e:f\\..\\..\\z.txt",
                           "\\\\localhost\\sh:are\\x.txt", "//localhost:1/share/x.txt", "\\\\?\\Volume{{a:b}}\\x.txt",
                           out + "\\NUL:", out + "\\nul :"):
                rule = _rule(action="file", target=target, template="txt")
                errors = [p for p in engine.lint(templates, rule, _database()) if p.template is None and p.severity == "error"]
                shown = engine.preview(rule, 0, templates=templates, params={}, database=_database(), files_root=out)
                _, findings = engine.fire("after_300", _database(), rules=[rule], templates=templates, params={},
                                          files_root=out)
                eq([f.type for f in findings], ["rx_file_write"], f"{target!r}: the fire refuses it")
                eq(shown.problem, (findings[0].type, findings[0].detail), f"{target!r}: …the preview says so")
                eq([p.where for p in errors], ["target"], f"{target!r}: …and so does the lint")
            eq(os.listdir(out), [], "nothing written")
            for target in ("\\\\.\\UNC\\localhost\\.\\rx_share", "\\\\localhost\\rx_share", "\\\\.\\\\" + out + "\\f3.txt"):
                rule = _rule(action="file", target=target, template="txt")     # C-024 round 23 (F2, F3): a share
                errors = [p for p in engine.lint(templates, rule, _database())  # root in any spelling; a device
                          if p.template is None and p.severity == "error"]      # path whose first name is empty
                shown = engine.preview(rule, 0, templates=templates, params={}, database=_database(), files_root=out)
                eq((shown.problem or ("",))[0], "rx_file_write", f"{target!r}: the fire refuses it")
                eq([p.where for p in errors], ["target"], f"{target!r}: …and so does the lint")
    _sandboxed(body)


def test_a_format_spec_is_tried_on_the_value_the_hole_yields():
    """C-025 refute round 6 (#3): a format spec was tried on ANY value (a text, an int, a float): `{where(src):>5}`,
    `{first(...):>5}`, `{unique(...):>5}`, `{count(src):s}`, a range var's `{$i:s}`, a table var's `{$r:>5}` linted
    clean while every fire fails (a list / dict - `[]` / `{}` when nothing is found, never blank - a float, an int,
    a row), and a spec only numbers take on a text column (`{$txt:,}`) failed on every row holding text. The kind the
    hole's expression yields is tried now - an ERROR where it is fixed, a WARNING on the values the rule's Database
    holds; an in-memory number (`{$n:,}`), numeric text under a conversion (`{$num:d}`) and a text spec stay clean."""
    def database():
        base = _database()
        base.add_table(Table("specs", columns=["uid", "txt", "num", "n"], key_columns=["txt"]))
        base["specs"].add(txt="abc", num="12", n=1200)          # (n: a number in memory - a staged cell)
        return base

    cases = (("{where(src):>5}", "", "error"), ('{first(src, $name = "none"):>5}', "", "error"),
             ("{unique(name, src):>5}", "", "error"), ("{count(src):s}", "", "error"), ("{len($txt):s}", "specs", "error"),
             ("@for $i in 1..2: {$i:s}", "", "error"), ("@for $r in specs: {$r:>5}", "", "error"),
             ("{$txt:,}", "specs", "warning"), ("{$txt:d}", "specs", "warning"), ("{$num:,}", "specs", "warning"),
             ("{count(src):>7}", "", None), ("{$txt:>5}", "specs", None), ("{$n:,}", "specs", None),
             ("{$num:d}", "specs", None), ("@for $r in specs: {$r.txt:>5}", "", None))

    def body():
        with tempfile.TemporaryDirectory() as out:
            for number, (text, source, severity) in enumerate(cases):
                name = f"t{number}"
                rule = _rule(action="file", source_table=source, target=f"o{number}.txt", template=name)
                found = [p.severity for p in engine.lint({name: text}, rule, database())
                         if p.template == name and "format spec" in p.message]
                eq(found, [severity] if severity else [], f"{text!r}: the lint")
                _, findings = engine.fire("after_300", database(), rules=[rule], templates={name: text}, params={},
                                          files_root=out)
                eq([f.type for f in findings], ["rx_bad_template"] if severity else [], f"{text!r}: the fire")
    _sandboxed(body)


def test_an_empty_sources_preview_keeps_the_fires_finding():
    """C-025 refute round 6 (#4): an add_rows rule over an EMPTY source table into a table the hook does not have -
    the fire reports rx_unknown_table (rows or none), the preview said only "no rows". The target is judged first."""
    database = _database()
    database.add_table(Table("empty", columns=["uid", "name"]))
    rule = _rule(source_table="empty", target="dstt")
    templates = {"rows": [{"label": "x"}]}

    def body():
        _, findings = engine.fire("after_300", database, rules=[rule], templates=templates, params={})
        shown = engine.preview(rule, 0, templates=templates, params={}, database=database)
        eq([f.type for f in findings], ["rx_unknown_table"], "(the fire)")
        eq(shown.problem, (findings[0].type, findings[0].detail), "the preview says the fire's finding")
    _sandboxed(body)


def test_a_row_read_warning_sits_on_its_own_token():
    """C-025 refute round 6 (#5): a missing column was found by searching its name from the call on - `{count(signals,
    "name" = $name)}` squiggled the string, `{lookup(signals, tag, first(nodes, $name = "x"), name)}` squiggled the
    inner first()'s `$name` (a column nodes HAS) for the lookup's missing `name`. The parser records each read's
    tokens now; each warning sits on its own."""
    tables = {"signals": ["uid", "tag", "addr"], "nodes": ["uid", "name"]}
    fields = {"_params", "_rule", "_db", "tag"}

    def placed(line):
        return [(line[p.start:p.end], p.start) for p in lint({"t": line}, start="t", fields=fields, tables=tables)
                if "not a column" in p.message or "not a table" in p.message]
    line = '{count(signals, "name" = $name)}'
    eq(placed(line), [("$name", line.index("$name"))], "on the $col, not the string")
    line = '{lookup(signals, tag, first(nodes, $name = "x"), name)}'
    eq(placed(line), [("name", line.rindex("name"))], "on the lookup's own column word")
    line = '{concat(count(signals, $x = "1"), count(signals, $x = "2"))}'
    eq(placed(line), [("$x", line.index("$x")), ("$x", line.rindex("$x"))], "each call's own")
    line = '{concat("nodez", count(nodez))}'
    eq(placed(line), [("nodez", line.rindex("nodez"))], "an unknown table on the call's table word")


if __name__ == "__main__":
    import sys
    sys.exit(run("template_builder", [
        ("lint_finds_every_render_error_on_its_line", test_lint_finds_every_render_error_on_its_line),
        ("lint_walks_every_branch", test_lint_walks_every_branch),
        ("context_lint_matches_the_strict_render", test_context_lint_matches_the_strict_render),
        ("predicates_are_lenient_so_their_unknowns_are_warnings",
         test_predicates_are_lenient_so_their_unknowns_are_warnings),
        ("positions_point_at_the_culprit", test_positions_point_at_the_culprit),
        ("silent_literals_and_boundary_lines", test_silent_literals_and_boundary_lines),
        ("the_shipped_worked_examples_lint_clean", test_the_shipped_worked_examples_lint_clean),
        ("preview_equals_the_fire", test_preview_equals_the_fire),
        ("preview_states", test_preview_states),
        ("engine_lint_judges_entries_and_rules", test_engine_lint_judges_entries_and_rules),
        ("format_specs_are_judged_in_every_branch", test_format_specs_are_judged_in_every_branch),
        ("use_depth_is_judged_whatever_the_order", test_use_depth_is_judged_whatever_the_order),
        ("preview_keeps_the_fires_guards", test_preview_keeps_the_fires_guards),
        ("has_business_mirrors_the_fires_no_op", test_has_business_mirrors_the_fires_no_op),
        ("preview_sees_the_in_hook_cascade", test_preview_sees_the_in_hook_cascade),
        ("windows_refused_target_characters", test_windows_refused_target_characters),
        ("drive_targets_are_the_fires_to_judge", test_drive_targets_are_the_fires_to_judge),
        ("every_target_shape_lint_equals_the_fire", test_every_target_shape_lint_equals_the_fire),
        ("a_lone_surrogate_is_what_the_fire_refuses", test_a_lone_surrogate_is_what_the_fire_refuses),
        ("a_data_functions_row_reads_are_judged", test_a_data_functions_row_reads_are_judged),
        ("format_specs_know_the_values_type", test_format_specs_know_the_values_type),
        ("a_field_name_utf8_cannot_store_is_the_templates_error", test_a_field_name_utf8_cannot_store_is_the_templates_error),
        ("device_prefixes_and_names_lint_equals_the_fire", test_device_prefixes_and_names_lint_equals_the_fire),
        ("node_of_reads_are_judged_as_every_data_functions", test_node_of_reads_are_judged_as_every_data_functions),
        ("a_lone_surrogate_is_judged_where_it_is_stored", test_a_lone_surrogate_is_judged_where_it_is_stored),
        ("an_in_row_warning_lands_on_its_own_call", test_an_in_row_warning_lands_on_its_own_call),
        ("a_colon_is_judged_as_written", test_a_colon_is_judged_as_written),
        ("a_format_spec_is_tried_on_the_value_the_hole_yields", test_a_format_spec_is_tried_on_the_value_the_hole_yields),
        ("an_empty_sources_preview_keeps_the_fires_finding", test_an_empty_sources_preview_keeps_the_fires_finding),
        ("a_row_read_warning_sits_on_its_own_token", test_a_row_read_warning_sits_on_its_own_token),
    ]))
