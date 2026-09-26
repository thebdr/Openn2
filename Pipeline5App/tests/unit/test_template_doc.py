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


def _tagged(doc, tag, language="scl"):
    return [doc.text[s:e] for t, s, e in td.spans(doc, language) if t == tag]


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
    ok('"P1"' not in _tagged(doc, "hl_str"), "the YAML layer stays out of a text template's body")
    ok("tx_error" not in {t for t, _s, _e in td.spans(doc, "scl")}, "no false error token (the spec is split off)")
    ok("REGION" not in _tagged(doc, "hl_key", language=None),
       "no language layer unless the system names one (System.template_language - no SCL baked in)")
    other = td.parse("q: |-\n  SELECT {$x} FROM t REGION\n")
    keys = [other.text[s:e] for t, s, e in td.spans(other, "sql") if t == "hl_key"]
    ok("SELECT" in keys and "REGION" not in keys, f"the system's OWN language - not SCL ({keys})")


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


_STYLES = r"""leaf: |2-
      PEC_{$i}();
    END {$nme}
tail: |
  kept {$a}

keep: |+
  plus {$b}

after: |-
  x
rows:
  - label: "{{\"of\": \"{$nme}\"}}"
    note: 'it''s {$nm}'
  - 1: "{$name}"
123: |-
  X {$zz}
"""


def test_positions_hold_for_every_scalar_style():
    """C-025 refute round 1: positions held only for plain `|-` blocks. An indentation indicator
    (`|2-` - YAML REQUIRES one when a body's first line is indented), an escaped double-quoted value
    (a JSON cell), `''` in single quotes, a `|` / `|+` block's trailing newlines, keys YAML types
    (`1:`, `123:`) - each placed exactly now, and none crashes the view."""
    from pipeline5.language.tempemplator import Problem
    doc = td.parse(_STYLES)
    eq(doc.error, None, "loads")
    eq(sorted((name, e.kind) for name, e in doc.entries.items()),
       [("123", "text"), ("after", "text"), ("keep", "text"), ("leaf", "text"), ("rows", "row"), ("tail", "text")],
       "the typed key 123 is the entry '123'")
    for name, entry in doc.entries.items():
        if entry.kind == "text":
            for number, line in enumerate(entry.text.split("\n")):
                start = entry.body.offset(number, 0)
                eq(doc.text[start:start + len(line)], line, f"{name} line {number + 1}")
    ok({"keep", "after", "rows"} <= set(_tagged(doc, "hl_key")), "a `|` / `|+` body does not swallow the next key")

    def placed(template, where, value, needle):
        start = value.index(needle)
        spot = td.place(doc, [Problem(template, where, start, start + len(needle), "m", "error")])[0]
        return doc.text[spot.start:spot.end]

    rows = doc.entries["rows"]
    eq(placed("rows", (1, "label"), rows.value_text[(1, "label")], "$nme"), "$nme", "an escaped JSON cell")
    eq(placed("rows", (1, "note"), rows.value_text[(1, "note")], "$nm"), "$nm", "a '' in single quotes")
    eq(placed("rows", (2, 1), rows.value_text[(2, "1")], "$name"), "$name", "a field YAML typed as the int 1")
    eq(placed(123, 1, doc.entries["123"].text, "$zz"), "$zz", "a template YAML typed as the int 123")
    fields = _tagged(doc, "tx_field")
    ok({"$i", "$nme", "$nm", "$name", "$zz"} <= set(fields), f"every hole highlighted ({fields})")
    problems = engine.lint(doc.templates)
    ok(all(p.start is not None or p.label == "rule" for p in td.place(doc, problems)), "the lint places")
    at = _STYLES.index('"{$name}') + len('"{$na')
    eq(td.completions(doc, at, td.Context(fields=frozenset({"name"})))[1], ["$name"], "completes inside a typed key")


def test_completions_stay_in_scope():
    """C-025 refute round 1: a `where` offered names it cannot see (its scope is the loop table's
    ROW), and a rule's fields were offered in templates the rule never renders."""
    text = "w: |-\n  @for $s in signals where $\n  x\n  @end\na: |-\n  {$k\nb: |-\n  {$k\n"
    doc = td.parse(text)
    ctx = td.Context(fields=frozenset({"kind", "_params", "_rule", "_db"}), tables={"signals": ["uid", "tag"]},
                     reach=frozenset({"w", "a"}))
    eq(td.completions(doc, text.index("where $") + 7, ctx)[1], ["$uid", "$tag"], "a `where`: the table's columns")
    eq(td.completions(doc, text.index("a: |-\n  {$k") + 11, ctx)[1], ["$kind"], "a rendered template: the fields")
    eq(td.completions(doc, text.index("b: |-\n  {$k") + 11, ctx)[1], [], "a template the rule never renders")
    eq(td.reach({"t": "@use u\n@for $i in 1..2: @use v", "u": "x", "v": "@use u", "w": "y"}, "t"),
       frozenset({"t", "u", "v"}), "reach follows @use - inline bodies too")


def test_the_session_models_the_run_plan():
    """C-025 refute round 1 + the implications check: the builder previewed against the Database/
    folder - the last SAVED state (later phases re-save it; a previous run's spawns in it) - not what
    the fire gets. The Session models the run-plan: the hook's declared loader (the system's own
    input, rebuilt in memory), a settled database-less hook (its record attached), the in-hook
    cascade; and it says what cannot be built, and when a document is not what a fire uses."""
    import tempfile
    from pipeline5 import config
    from pipeline5.truth.database import Database
    from pipeline5.truth.table import Table

    def staged(system):
        src = Table("src", columns=["uid", "kind", "name"], key_columns=["name"])
        src.add(kind="door", name="D1")
        src.add(kind="motor", name="M1")
        return Database([src, Table("dst", columns=["uid", "label", "spawned_by", "source_uid"], key_columns=["label"])])

    rules = [{"name": "hdr", "fire_when": "before_300", "source_table": "", "condition": "", "action": "file",
              "target": "h.txt", "template": "t"},
             {"name": "A", "fire_when": "after_300", "source_table": "src", "condition": "", "action": "add_rows",
              "target": "dst", "template": "rows"},
             {"name": "B", "fire_when": "after_300", "source_table": "dst", "condition": "", "action": "file",
              "target": "{$label}.txt", "template": "t"}]
    doc = td.parse('t: |-\n  row {$label}\nrows:\n  - label: "L-{$name}"\n')
    hooks = {"before_300": None, "after_300": staged}
    original = config.database_dir
    with tempfile.TemporaryDirectory() as sandbox:
        config.database_dir = lambda: sandbox
        try:
            session = td.Session(None, rows=rules, hooks=hooks, params={})
            ok(session.loaded("before_300") and not session.loaded("after_300"), "built on demand (a worker's job)")
            base = session.base("after_300")
            ok("chain_reactions_log" not in base.names(), "the base is the loader's own output")
            second = session.rules[2]
            seen = session.view(second, doc.templates)[0]
            ok("chain_reactions_log" in seen.names(), "a before_300 rule is settled in: its record attached")
            ok("chain_reactions_log" not in base.names(), "…into a COPY - the built Database stays the loader's")
            eq([(r["hook"], r["rule"], r["outcome"]) for r in seen["chain_reactions_log"]],
               [("before_300", "hdr", "rx_bad_template")],
               "…with THIS run's before_300 audit - a dry fire of it (its `$label` is missing: no source row)")
            eq([f["type"] for f in seen["validation_issues"]], ["rx_bad_template"], "…and its finding recorded")
            eq(session.row_count(second, doc.templates), 2, "B sees A's spawns - the in-hook cascade")
            preview = session.preview_text(doc, second, 1)
            ok(preview.endswith("row L-M1"), preview)
            eq(len(base["dst"]), 0, "the cascade never touches the hook's Database")
            quiet = td.Session(None, rows=rules[1:], hooks=hooks, params={})
            ok("chain_reactions_log" not in quiet.view(quiet.rules[1], doc.templates)[0].names(),
               "no before_300 business: no settle")
            broken = td.Session(None, rows=rules, hooks={"after_300": lambda system: 1 / 0}, params={})
            eq(broken.base("after_300"), None, "a Database that cannot be built")
            ok(any("cannot be built" in note for note in broken.notes), f"…is noted: {broken.notes}")
            text = broken.preview_text(doc, broken.rules[2], 0)
            ok(text.startswith("the run stops before after_300 fires - its Database cannot be built (division by "
                               "zero)") and "rx_unknown_table" not in text and "does NOT match" not in text,
               f"a Database that cannot be built stops the run: no findings of a fire that never happens: {text!r}")
            eq([(p.severity, p.label) for p in broken.check(doc, broken.rules[2])], [("warning", "rule")],
               "…the check says so, once")
            missing = td.Session(None, rows=rules[:2] + [{**rules[2], "source_table": "nope"}], hooks=hooks, params={})
            text = missing.preview_text(doc, missing.rules[2], 0)
            ok("rx_unknown_table" in text and "does NOT match" not in text,
               f"a fire that stops BEFORE the condition is not called a 'no match': {text!r}")
            ok(any("declares no reaction hooks" in note for note in td.Session(None, rows=rules, hooks={}, params={}).notes),
               "a system that declares no hooks is noted")
            elsewhere = td.Session(os.path.join(sandbox, "other.yaml"), rows=rules, hooks=hooks, params={})
            elsewhere.active = os.path.join(sandbox, "active.yaml")
            ok(elsewhere.preview_text(doc, elsewhere.rules[2], 0).startswith("note: a fire uses"),
               "a document a fire does not use says so")
        finally:
            config.database_dir = original


def test_folded_plain_scalars_are_approximate():
    """C-025 refute round 2 (#7): a multi-line PLAIN scalar is FOLDED by YAML - one line in the value,
    several in the document - yet was flagged exact: its squiggle landed on the wrong characters. It
    is approximate now: a problem sits on its first line, labelled so, and the template layer paints
    no colours at offsets that do not hold."""
    from pipeline5.language.tempemplator import Problem
    text = "rows:\n  - label: L-{$name}\n      -{$mnemonc}\nt: X {$nme}\n  Y {$kind}\nok: Z {$zz}\n"
    doc = td.parse(text)
    eq(doc.error, None, "loads")
    rows, folded = doc.entries["rows"], doc.entries["t"]
    eq((rows.value_text[(1, "label")], folded.text), ("L-{$name} -{$mnemonc}", "X {$nme} Y {$kind}"),
       "YAML folds both")
    ok(not rows.values[(1, "label")].exact and not folded.body.exact, "…so neither is exact")
    ok(doc.entries["ok"].body.exact, "a one-line plain scalar stays exact")
    value = rows.value_text[(1, "label")]
    at = value.index("$mnemonc")
    spot = td.place(doc, [Problem("rows", (1, "label"), at, at + 8, "m", "error")])[0]
    eq((doc.text[spot.start:spot.end], spot.label), ("L-{$name}", "rows entry 1 label (approximate)"),
       "a row value's problem: its first line, labelled approximate")
    at = folded.text.index("$kind")
    spot = td.place(doc, [Problem("t", 1, at, at + 5, "m", "error")])[0]
    eq((doc.text[spot.start:spot.end], spot.label), ("X {$nme}", "t line 1 (approximate)"), "…a text template's too")
    fields = _tagged(doc, "tx_field")
    eq(fields, ["$zz"], "no template colours on the folded scalars - only where the offsets hold")


def test_a_data_functions_predicate_completes_its_tables_columns():
    """C-025 refute round 2 (#5): inside `count(<table>, ...)` / `where(` / `first(` the predicate reads
    that table's ROW - yet the completion offered the rule's fields (the round-1 fix covered `@for ...
    where` only). It offers the table's columns now - the innermost call's - and an ordinary call or
    the table argument itself keeps the ordinary names."""
    text = ("cab: |-\n  {$cabinet_id}: {count(signals, $\n"
            "two: |-\n  {first(signals, $script_type = \"A\" and count(diagnosis_cabinets, $\n"
            "own: |-\n  {upper($\n"
            "quo: |-\n  {where(signals, $mnemonic = 'a)b' and $\n")
    doc = td.parse(text)
    ctx = td.Context(fields=frozenset({"_params", "_rule", "_db", "cabinet_id", "fld"}),
                     tables={"signals": ["uid", "mnemonic", "script_type"], "diagnosis_cabinets": ["cabinet_id", "fld"]},
                     reach=None)

    def offered(needle):
        return td.completions(doc, text.index(needle) + len(needle), ctx)[1]
    eq(offered("count(signals, $"), ["$uid", "$mnemonic", "$script_type"], "count's predicate: the signals ROW")
    eq(offered("count(diagnosis_cabinets, $"), ["$cabinet_id", "$fld"], "the innermost call's table")
    eq(offered("upper($"), ["$_params", "$_rule", "$cabinet_id", "$fld"], "an ordinary call: the rule's names")
    eq(offered("'a)b' and $"), ["$uid", "$mnemonic", "$script_type"], "a quoted string's ')' is not the call's")


def test_unreadable_params_block_as_the_fire_blocks():
    """C-025 refute round 2 (#6): with project_params.yaml unreadable the builder substituted {} and
    previewed a render, while the fire BLOCKS every rule of the hook (rx_params_unreadable) and writes
    nothing. The lint and the preview say the fire's finding now."""
    import tempfile
    from pipeline5 import config
    rules = [{"name": "hdr", "fire_when": "before_300", "source_table": "", "condition": "", "action": "file",
              "target": "h.txt", "template": "t"}]
    doc = td.parse("t: |-\n  HEADER [{$_params.project_code}]\n")
    original = config.load_params

    def unreadable(path=None):
        raise ValueError("while parsing a flow sequence: broken: [unclosed")
    config.load_params = unreadable
    try:
        session = td.Session(None, rows=rules, hooks={"before_300": None, "after_300": None})
        rule = session.rules[0]
        errors = [p.message for p in session.check(doc, rule) if p.severity == "error"]
        ok(len(errors) == 1 and "rx_params_unreadable" in errors[0] and "[unclosed" in errors[0], f"the lint: {errors}")
        shown = session.preview_text(doc, rule, 0)
        ok(shown.startswith("rx_params_unreadable") and "APPEND" not in shown, f"the preview: {shown!r}")
        with tempfile.TemporaryDirectory() as out:
            _deferred, findings = engine.fire("before_300", None, rules=rules, templates=doc.templates,
                                              files_root=out, hooks=("before_300", "after_300"))
            eq(([f.type for f in findings], os.listdir(out)), (["rx_params_unreadable"], []),
               "the fire: blocked, nothing written")
        from pipeline5.truth.database import Database
        from pipeline5.truth.table import Table
        later = rules + [{"name": "A", "fire_when": "after_300", "source_table": "src", "condition": "",
                          "action": "file", "target": "a.txt", "template": "t"}]
        original_dir = config.database_dir
        with tempfile.TemporaryDirectory() as sandbox:
            config.database_dir = lambda: sandbox
            try:
                both = td.Session(None, rows=later, hooks={
                    "before_300": None, "after_300": lambda system: Database([Table("src", columns=["uid", "name"])])})
                seen = both.view(both.rules[1], doc.templates)[0]
                eq([(r["rule"], r["outcome"]) for r in seen["chain_reactions_log"]], [("hdr", "rx_params_unreadable")],
                   "the before_300 settled into after_300's Database: its dry fire blocked, as the run's is")
                spawning = later + [{"name": "S", "fire_when": "after_300", "source_table": "src", "condition": "",
                                     "action": "add_rows", "target": "dst", "template": "rows"},
                                    {"name": "D", "fire_when": "after_300", "source_table": "dst", "condition": "",
                                     "action": "file", "target": "d.txt", "template": "t"}]
                src = Table("src", columns=["uid", "name"], key_columns=["name"])
                src.add(name="N1")
                cascade = td.Session(None, rows=spawning, hooks={"before_300": None, "after_300": lambda system: Database(
                    [src, Table("dst", columns=["uid", "label", "spawned_by", "source_uid"], key_columns=["label"])])})
                eq(cascade.row_count(cascade.rules[3], {"rows": [{"label": "L-{$name}"}], "t": "x"}), 0,
                   "a blocked fire spawns nothing: no cascade over params that do not load")
            finally:
                config.database_dir = original_dir
    finally:
        config.load_params = original


def test_the_dry_settle_writes_nothing():
    """The Session models a settled before_300 with a DRY fire of it - an absolute file target included
    (a scratch output root did not catch one: every view would have appended to the real file). The
    settled audit counts the lines a run would write; nothing is written."""
    import tempfile
    from pipeline5 import config
    from pipeline5.truth.database import Database
    from pipeline5.truth.table import Table
    with tempfile.TemporaryDirectory() as sandbox, tempfile.TemporaryDirectory() as elsewhere:
        absolute = os.path.join(elsewhere, "header.txt").replace("\\", "/")
        rules = [{"name": "hdr", "fire_when": "before_300", "source_table": "", "condition": "", "action": "file",
                  "target": absolute, "template": "t"},
                 {"name": "A", "fire_when": "after_300", "source_table": "src", "condition": "", "action": "file",
                  "target": "a.txt", "template": "t"}]
        doc = td.parse("t: |-\n  HEADER {$_rule.hook}\n")
        original_dir, original_out = config.database_dir, config.output_root
        config.database_dir, config.output_root = (lambda: sandbox), (lambda: os.path.join(sandbox, "out"))
        try:
            session = td.Session(None, rows=rules, hooks={
                "before_300": None, "after_300": lambda system: Database([Table("src", columns=["uid", "name"])])},
                params={})
            seen = session.view(session.rules[1], doc.templates)[0]
            eq([(r["rule"], r["created"], r["outcome"]) for r in seen["chain_reactions_log"]], [("hdr", 1, "ok")],
               "the settled audit: the line a run writes, counted")
            eq((os.listdir(elsewhere), os.path.exists(os.path.join(sandbox, "out"))), ([], False), "…nothing written")
        finally:
            config.database_dir, config.output_root = original_dir, original_out


def test_a_quoted_template_with_newline_escapes_is_exact():
    """C-025 refute round 3 (F6): a double-quoted text template's `\\n` escapes are value LINES on one
    document line - `offset` ignored the line for a character-mapped scalar, so line 2's squiggle, colours
    and completions landed on line 1's characters. They map through the decoded value now - an escape
    earlier on the same line (`\\"`) included."""
    from pipeline5.language.tempemplator import Problem
    text = 'hdr: "HEADER {$_rule.hook}\\nL2 \\"x\\" {$nme} END"\n'
    doc = td.parse(text)
    body = doc.entries["hdr"]
    eq(body.text, 'HEADER {$_rule.hook}\nL2 "x" {$nme} END', "the value: two lines")
    ok(body.body.exact and body.body.chars is not None, "exact, character-mapped")
    column = 'L2 "x" {$nme} END'.index("$nme")
    spot = td.place(doc, [Problem("hdr", 2, column, column + 4, "m", "error")])[0]
    eq((doc.text[spot.start:spot.end], spot.label), ("$nme", "hdr line 2"), "line 2's problem on its culprit")
    eq(sorted(_tagged(doc, "tx_field")), ["$_rule.hook", "$nme"], "the template colours on their holes")
    at = text.index("{$n") + 3
    eq(td.completions(doc, at, td.Context(fields=frozenset({"name", "_params", "_rule", "_db"})))[1], ["$name"],
       "a completion on line 2")


def test_other_line_breaks_are_approximate():
    """C-025 refute round 4 (F3): the renderer splits a template on EVERY line break (`str.splitlines`:
    `\\r`, `\\f`, `\\v`, U+2028 ...), the view on `\\n` only - a `\\r` escape's problem landed on the
    closing quote. Such a scalar is approximate now: its first line, labelled so, no colours."""
    from pipeline5.language.tempemplator import Problem
    text = 'hdr: "HEADER\\rX {$nme} END"\nplain: A {$zz}\u2029B\n'
    doc = td.parse(text)
    for name, line in (("hdr", 2), ("plain", 1)):
        entry = doc.entries[name]
        ok(not entry.body.exact, f"{name}: approximate")
        spot = td.place(doc, [Problem(name, line, 0, 1, "m", "error")])[0]
        eq(spot.label, f"{name} line {line} (approximate)", f"{name}: labelled so")
    eq(_tagged(doc, "tx_field"), [], "no template colours at offsets that do not hold")


def test_a_reload_discards_the_build_it_overtook():
    """C-025 refute round 2 (#8): a Reload during an in-flight build KEPT the stale build (the builder
    then showed 1 signal row while the documents had 5). The Session numbers its builds: one started
    before a reload is discarded, and the next question rebuilds against the reloaded state."""
    import threading
    from pipeline5.truth.database import Database
    from pipeline5.truth.table import Table
    entered, release, built = threading.Event(), threading.Event(), []

    def loader(system):
        built.append(len(built) + 1)
        entered.set()
        release.wait(10)
        table = Table("src", columns=["uid", "name"], key_columns=["name"])
        for number in range(len(built)):
            table.add(name=f"N{number}")
        return Database([table])

    rules = [{"name": "A", "fire_when": "after_300", "source_table": "src", "condition": "", "action": "file",
              "target": "x.txt", "template": "t"}]
    session = td.Session(None, rows=rules, hooks={"after_300": loader}, params={})
    worker = threading.Thread(target=session.base, args=("after_300",))
    worker.start()
    ok(entered.wait(10), "a build is in flight")
    session.reload()                                         # e.g. the rules or the documents changed
    release.set()
    worker.join(10)
    ok(not session.loaded("after_300"), "the build the reload overtook is not kept")
    eq(len(session.base("after_300")["src"]), 2, "the next question rebuilds")
    eq(built, [1, 2], "…once more")
    entered.clear()                                           # C-025 refute round 3 (F8): the same, through
    release.clear()                                           # a VIEW - it was cached over the stale build
    del built[:]
    session = td.Session(None, rows=rules, hooks={"after_300": loader}, params={})
    templates = {"t": "row {$name}"}
    worker = threading.Thread(target=session.row_count, args=(session.rules[0], templates))
    worker.start()
    ok(entered.wait(10), "a view's build is in flight")
    session.reload()
    release.set()
    worker.join(10)
    eq(session.row_count(session.rules[0], templates), 2, "a view over the overtaken build is not cached either")
    import sys                                                # C-025 refute round 4 (F5): a reload landing
    release.set()                                             # right after view()'s generation check

    class ReloadAfterTheCheck:
        """The Session's lock, reloading on the SECOND release inside one view() call - after its check."""
        def __init__(self, target):
            self.real, self.target, self.count, self.armed = threading.Lock(), target, 0, True

        def __enter__(self):
            self.real.acquire()

        def __exit__(self, *exc):
            self.real.release()
            if self.armed and sys._getframe(1).f_code.co_name == "view":
                self.count += 1
                if self.count == 2:
                    self.armed = False
                    self.target.reload()
    session = td.Session(None, rows=rules, hooks={"after_300": loader}, params={})
    session.base("after_300")                                 # built - view() takes the lock twice
    session._lock = ReloadAfterTheCheck(session)
    session.row_count(session.rules[0], templates)
    ok(not session._lock.armed, "(the reload landed inside view())")
    count = session.row_count(session.rules[0], templates)
    eq(count, len(session.base("after_300")["src"]), "the reload's fresh build - nothing stale cached")


if __name__ == "__main__":
    import sys
    sys.exit(run("template_doc", [
        ("positions_are_exact", test_positions_are_exact),
        ("a_yaml_error_is_located", test_a_yaml_error_is_located),
        ("two_layer_highlight", test_two_layer_highlight),
        ("problems_land_on_the_culprit", test_problems_land_on_the_culprit),
        ("completions", test_completions),
        ("positions_hold_for_every_scalar_style", test_positions_hold_for_every_scalar_style),
        ("completions_stay_in_scope", test_completions_stay_in_scope),
        ("the_session_models_the_run_plan", test_the_session_models_the_run_plan),
        ("folded_plain_scalars_are_approximate", test_folded_plain_scalars_are_approximate),
        ("a_data_functions_predicate_completes_its_tables_columns",
         test_a_data_functions_predicate_completes_its_tables_columns),
        ("unreadable_params_block_as_the_fire_blocks", test_unreadable_params_block_as_the_fire_blocks),
        ("the_dry_settle_writes_nothing", test_the_dry_settle_writes_nothing),
        ("a_quoted_template_with_newline_escapes_is_exact", test_a_quoted_template_with_newline_escapes_is_exact),
        ("a_reload_discards_the_build_it_overtook", test_a_reload_discards_the_build_it_overtook),
        ("other_line_breaks_are_approximate", test_other_line_breaks_are_approximate),
    ]))
