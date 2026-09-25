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
    ]))
