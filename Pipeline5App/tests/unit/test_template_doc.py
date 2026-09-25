"""The templates.yaml editing model (workbench/template_doc.py - P-012): positions, the two-layer
highlight, problem placement, completions. Tk-free. The contract: every position is EXACT - a text
template's line maps back onto the document character for character, a placed lint problem covers
precisely the culprit's text, and the tags sit on the constructs they name."""
import os

from _harness import run, eq, ok
from pipeline5.phases.chain_reactions import engine
from pipeline5.workbench import template_doc as td

_SHIPPED = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                        "pipeline5", "systems", "plc_based", "siemens_s7", "safety", "config_project",
                        "chain_reactions", "templates.yaml")

_DOC = """# a header comment
belt: |-
  REGION {$name}
  @for $i in 1..{$n}: PEC{$i}();
  @for $r in signals where $tag = "P1"
    X := {{ {$r.tag} }};
  @end
  @use leaf
  END_REGION
leaf: |-
  // leaf {$name:>8}
rows:
  - label: "spawn-{$name}"
    desc: plain {$kind}
other: 7
"""


def _tagged(doc, tag):
    return [doc.text[s:e] for t, s, e in td.spans(doc) if t == tag]


def test_positions_are_exact():
    """Every text-template line maps back onto the document character for character - on the
    authoring manual itself (comments, blank lines, the worked examples)."""
    with open(_SHIPPED, encoding="utf-8") as handle:
        text = handle.read().replace("\r\n", "\n")
    for doc_text in (text, _DOC):
        doc = td.parse(doc_text)
        eq(doc.error, None, "loads")
        for name, entry in doc.entries.items():
            if entry.kind == "text":
                for number, line in enumerate(doc.templates[name].split("\n")):
                    start = entry.body.offset(number, 0)
                    eq(doc.text[start:start + len(line)], line, f"{name} line {number + 1}")
            eq(doc.text[slice(*entry.key)], name, f"{name}: the key")
    doc = td.parse(_DOC)
    eq(sorted((n, e.kind) for n, e in doc.entries.items()),
       [("belt", "text"), ("leaf", "text"), ("other", "other"), ("rows", "row")], "the kinds")
    rows = doc.entries["rows"]
    for (number, column), scalar in rows.values.items():
        value = doc.templates["rows"][number - 1][column]
        eq(doc.text[scalar.at(0, value):scalar.at(len(value), value)], value, f"row value {column}")


def test_a_yaml_error_is_located():
    """The engine's rx_templates_unreadable, placed where the loader stopped."""
    doc = td.parse("ok: |-\n  fine\nbad: [unclosed\nmore: x\n")
    ok(doc.error is not None and doc.templates == {}, "does not load")
    placed = td.place(doc, [])
    eq((placed[0].label, placed[0].severity), ("templates.yaml", "error"), "one problem, first")
    ok(doc.text[placed[0].start:].startswith(("more", "\n", "bad", " [")) or placed[0].start >= doc.text.index("bad"),
       f"at the broken line or after it ({placed[0].start})")
    eq(td.parse("- a\n- b\n").error[1], "templates.yaml must be a mapping of named templates", "a list")


def test_two_layer_highlight():
    """YAML for the structure, SCL under the text templates, the template constructs on top."""
    doc = td.parse(_DOC)
    ok("belt" in _tagged(doc, "hl_key") and "rows" in _tagged(doc, "hl_key"), "YAML keys")
    ok("# a header comment" in _tagged(doc, "hl_cmt"), "a YAML comment")
    ok("REGION" in _tagged(doc, "hl_key") and "END_REGION" in _tagged(doc, "hl_key"), "SCL keywords in a body")
    ok("// leaf {$name:>8}" in _tagged(doc, "hl_cmt"), "an SCL comment in a body")
    eq(sorted(set(_tagged(doc, "tp_directive"))), ["@end", "@for", "@use", "in", "where"], "directives + keywords")
    eq(_tagged(doc, "tp_ref"), ["leaf"], "an @use reference")
    eq(_tagged(doc, "tp_table"), ["signals"], "a @for table")
    eq(_tagged(doc, "tp_literal"), ["{{", "}}"], "the doubled braces")
    fields = _tagged(doc, "tx_field")
    for name in ("$name", "$n", "$i", "$r", "$tag", "$r.tag", "$kind"):
        ok(name in fields, f"{name} as a field ({fields})")
    eq(_tagged(doc, "tp_spec"), [">8"], "a format spec")
    ok(_tagged(doc, "tx_string") == ['"P1"'], "a predicate string")
    ok("tx_error" not in {t for t, _s, _e in td.spans(doc)}, "no false error token (the spec is split off)")


def test_problems_land_on_the_culprit():
    """engine.lint's problems, placed: the squiggle covers exactly the offending text."""
    text = _DOC.replace("{$r.tag}", "{$r.tagg}").replace("@use leaf", "@use leef").replace(
        "spawn-{$name}", "spawn-{$name}}")
    doc = td.parse(text)
    tables = {"signals": ["uid", "tag"]}
    rule = engine.compile_rules([{"name": "r", "fire_when": "after_300", "source_table": "", "condition": "",
                                  "action": "file", "target": "x.scl", "template": "belt"}])[0][0]
    problems = engine.lint(doc.templates, rule, None, hooks=("before_300",))    # (a hook never fired)
    placed = {doc.text[p.start:p.end]: p for p in td.place(doc, problems) if p.start is not None}
    ok("leef" in placed and "unknown template" in placed["leef"].message, f"the @use name ({sorted(placed)})")
    ok("}" in placed and placed["}"].label == "rows entry 1 label", "the lone brace in a row value")
    ok("other" in placed and "neither" in placed["other"].message, "a whole entry at its name")
    ok(any(p.start is None and p.label == "rule" for p in td.place(doc, problems)), "a rule problem, unplaced")
    problems = engine.lint(doc.templates)
    ok(not any("tagg" in p.message for p in problems), "without the rule's tables no column is judged")


def test_completions():
    """What fits at the cursor - each from the document or the rule's context, never invented."""
    doc = td.parse(_DOC)
    context = td.Context(fields=frozenset({"name", "n", "kind", "_params", "_rule", "_db"}),
                         tables={"signals": ["uid", "tag", "type"]}, params={"project_code": "8X", "rx": {"on": "1"}})

    def at(marker, text=_DOC, context=context):
        doc = td.parse(text)
        return td.completions(doc, text.index(marker) + len(marker), context)

    eq(at("  @us", _DOC.replace("@use leaf", "@us"))[1], ["@use"], "a directive")
    eq(at("  @use ", _DOC.replace("@use leaf", "@use "))[1], ["leaf"], "@use: the other text templates")
    eq(at("in sig", _DOC.replace("in signals", "in sig"))[1], ["signals"], "a table after `in`")
    start, found = at("REGION {$n")
    eq((found, _DOC[start:start + 2]), (["$name"], "$n"), "a field stem inside a hole - the stem replaced")
    eq(at("    X := {{ {$r.")[1], ["$r.uid", "$r.tag", "$r.type"], "a loop row's columns (declared order)")
    eq(at("{$_params.", _DOC.replace("REGION {$name}", "REGION {$_params.") )[1],
       ["$_params.project_code", "$_params.rx"], "the project params")
    eq(at("{$_params.rx.", _DOC.replace("REGION {$name}", "REGION {$_params.rx."))[1], ["$_params.rx.on"], "nested")
    ok("coalesce" in at("{coal", _DOC.replace("REGION {$name}", "REGION {coal"))[1], "a function")
    found = at("PEC{$")[1]
    ok("$i" in found and "$name" in found and "$_db" not in found, f"the loop var + the rule's fields ({found})")
    eq(at("REGI")[1], [], "plain target text: nothing")
    eq(at("# a hea")[1], [], "the YAML structure: nothing")
    eq(at("spawn-{$na")[1], ["$name"], "a row value's hole")
    eq(at("REGION {$n", context=None)[1], [], "no rule chosen: no fields to offer")


if __name__ == "__main__":
    import sys
    sys.exit(run("template_doc", [
        ("positions_are_exact", test_positions_are_exact),
        ("a_yaml_error_is_located", test_a_yaml_error_is_located),
        ("two_layer_highlight", test_two_layer_highlight),
        ("problems_land_on_the_culprit", test_problems_land_on_the_culprit),
        ("completions", test_completions),
    ]))
