"""The chain-reaction engine (phases/chain_reactions/engine.py) - rule compilation, the fire()
lifecycle (match -> spawn/append -> audit log -> save), provenance, the strict empty-hook no-op,
and every failure surfacing as a located ERRR finding - never silent, never a crash (refuter
round 6's B1-B4 pinned here). Hermetic: synthetic tables + injected rules/templates; the database
dir is sandboxed."""
import os
import tempfile

from _harness import run, eq, ok
from pipeline5 import config
from pipeline5.config import params as p5params
from pipeline5.phases.chain_reactions import engine
from pipeline5.truth.database import Database
from pipeline5.truth.table import Table


def _db():
    src = Table("src", columns=["uid", "kind", "name"], key_columns=["name"])
    src.add(kind="door", name="D1")
    src.add(kind="door", name="D2")
    src.add(kind="motor", name="M1")
    dst = Table("dst", columns=["uid", "label", "spawned_by", "source_uid"], key_columns=["label"])
    return Database([src, dst])


def _rule(**over):
    row = {"name": "r1", "fire_when": "after_300", "source_table": "src",
           "condition": '$kind = "door"', "action": "add_rows", "target": "dst",
           "template": "rows", "comment": ""}
    row.update(over)
    return row


_ROW_TPL = {"rows": [{"label": "spawn-{$name}"}]}


def _sandboxed(fn):
    def wrapped():
        original = config.database_dir
        with tempfile.TemporaryDirectory() as sandbox:
            config.database_dir = lambda: sandbox
            try:
                fn(sandbox)
            finally:
                config.database_dir = original
    return wrapped


def _log(database):
    return [(r["hook"], r["rule"], r["matches"], r["created"], r["outcome"])
            for r in database[engine.LOG_TABLE]]


def test_compile_validates_and_drops_bad_rows():
    rules, findings = engine.compile_rules([
        _rule(),
        _rule(name="bad1", fire_when="sometime"),
        _rule(name="bad2", action="explode"),
        _rule(name="bad3", target=""),
        _rule(name="bad4", template=""),
        {"name": "", "fire_when": "after_300"},
    ])
    eq([r.name for r in rules], ["r1"], "only the valid rule compiles")
    eq(rules[0].phase, 300, "the hook's phase number is derived")
    bad = [f for f in findings if f.type == "rx_bad_rule"]
    eq(sorted(f.location for f in bad), ["<unnamed rule>", "bad1", "bad2", "bad3", "bad4"],
       "each malformed row is a located finding (a nameless one still locates)")
    ok(all(f.severity == "ERRR" for f in findings), "rule failures are ERRR (skip + continue)")


def test_unnamed_and_uncompilable_rules_are_caught_at_compile():
    """B4 (refuter round 6): a row that is otherwise VALID but has no name used to vanish in the
    loader; a condition typo used to hide behind an empty source table. Both are compile findings
    now - the rule is dropped, the finding locates it."""
    rules, findings = engine.compile_rules([
        _rule(name=""),                                   # everything valid except the name
        _rule(name="c1", condition="let("),               # truncated expression
        _rule(name="c2", condition="$name ~ /(D/"),       # a bad regex (raised re.error before)
        _rule(name="ok1"),
    ])
    eq([r.name for r in rules], ["ok1"], "the nameless + the two uncompilable rules are dropped")
    got = sorted((f.type, f.location) for f in findings)
    eq(got, [("rx_bad_condition", "c1"), ("rx_bad_condition", "c2"), ("rx_bad_rule", "<unnamed rule>")],
       "each is a located compile finding")
    unnamed = [f for f in findings if f.type == "rx_bad_rule"][0]
    ok("name is empty" in unnamed.detail and "'after_300'" in unnamed.detail,
       "the nameless finding carries the row's hook/action/target so the author can find it")


def test_loader_passes_nameless_rows_to_the_compiler():
    """B4a: `load_reactions` used to DROP a row with an empty name before the compiler saw it.
    Only fully blank lines are skipped now."""
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "reactions.csv")
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write("name,fire_when,source_table,condition,action,target,template,comment\n"
                         ",after_300,,,file,rx/probe.txt,probe_txt,forgot the name\n"
                         ",,,,,,,\n")
        from pipeline5.config import loaders
        real_find = loaders.find
        loaders.find = lambda rel: path if rel == "chain_reactions/reactions.csv" else real_find(rel)
        try:
            rows = config.load_reactions()
        finally:
            loaders.find = real_find
    eq(len(rows), 1, "the blank line is skipped, the nameless rule row is KEPT")
    _rules, findings = engine.compile_rules(rows)
    eq([f.type for f in findings], ["rx_bad_rule"], "…and the compiler reports it")


def test_fire_empty_hook_is_a_strict_noop(sandbox=None):
    def body(sandbox):
        database = _db()
        out, findings = engine.fire("after_300", database, rules=[], templates={}, params={})
        ok(out is database and findings == [], "no rules -> the same database, no findings")
        ok(engine.LOG_TABLE not in database, "no log table materialized")
        eq(os.listdir(sandbox), [], "NOTHING was written to disk (the byte-parity guarantee)")
        # rules for ANOTHER hook only (a clean index) -> still the strict no-op here
        out, findings = engine.fire("after_300", database, rules=[_rule(name="cold", fire_when="after_500")],
                                    templates={}, params={})
        ok(out is database and findings == [], "another hook's clean rule is not this hook's business")
        eq(os.listdir(sandbox), [], "…nothing written")
        # the never-silent guarantee: a malformed rule naming NO hook (it can never activate) is an
        # INDEX problem - every hook's business: it surfaces (refuter round 2: the drop-the-findings
        # mutant dies here) AND is recorded (round-6 implications: rendered-only was a silent record)
        out, findings = engine.fire("after_300", database,
                                    rules=[_rule(name="mal", fire_when="whenever"),
                                           _rule(name="cold", fire_when="after_500")],
                                    templates={}, params={})
        eq([(x.type, x.location) for x in findings], [("rx_bad_rule", "mal")],
           "the compile finding propagates even when this hook fires nothing")
        eq([r["type"] for r in database["validation_issues"]], ["rx_bad_rule"], "…and is recorded")
        eq(_log(database), [], "…with no audit rows (nothing fired)")
    _sandboxed(body)()


def test_rules_on_hooks_the_run_plan_never_fires_are_reported():
    """Round-6 implications: a rule on a hook nothing fires (`after_520`) used to compile clean and
    wait forever, silently. The run-plan passes its `hooks`; any other hook is `rx_unfired_hook`
    (an index problem: rendered at every fire, recorded once) and the rule never runs."""
    def body(sandbox):
        database = _db()
        rules = [_rule(), _rule(name="cold", fire_when="after_520"),
                 _rule(name="mal", fire_when="after_520", action="explode")]   # malformed AND unfired
        database, findings = engine.fire("after_300", database, rules=rules, templates=_ROW_TPL,
                                         params={}, hooks=("before_300", "after_300"))
        got = sorted((x.type, x.location) for x in findings)
        eq(got, [("rx_bad_rule", "mal"), ("rx_unfired_hook", "cold")], "both surface")
        ok("before_300, after_300" in [x for x in findings if x.type == "rx_unfired_hook"][0].detail,
           "…naming the hooks this run-plan does fire")
        eq(_log(database), [("after_300", "r1", 2, 2, "ok")], "the declared hook's rule still fires")
        eq(sorted(r["type"] for r in database["validation_issues"]), ["rx_bad_rule", "rx_unfired_hook"],
           "an undeclared hook's malformed rule is an index problem too - recorded here")
        # without `hooks` (a caller that declares nothing) there is no unfired check
        _, findings = engine.fire("after_300", _db(), rules=[_rule(name="cold", fire_when="after_520")],
                                  templates=_ROW_TPL, params={})
        eq(findings, [], "no declared hooks -> nothing to compare against")
    _sandboxed(body)()


def test_compile_never_crashes_a_hook():
    """Refuter round 7 B1: the rule index is compiled at EVERY hook's fire, and a condition the expr
    checker could not digest (`1.3` typed for the slice `1:3` - a raw ValueError) crashed every hook,
    even rule-less ones, and run_staging with them. It is a rx_bad_condition now; a row the compiler
    cannot even read is an index-problem rx_bad_rule named by its position."""
    rules, findings = engine.compile_rules([
        _rule(name="slice", condition='extract($name, /(\\d+)/, 1.3) = "1"'),
        None,                                             # an unreadable row (not a mapping at all)
        _rule(name="ok1"),
    ])
    eq([r.name for r in rules], ["ok1"], "the uncompilable rule and the unreadable row are dropped")
    eq(sorted((f.type, f.location) for f in findings),
       [("rx_bad_condition", "slice"), ("rx_bad_rule", "<row 2>")], "each is a located finding")
    deferred, findings = engine.fire("before_300", None, rules=[_rule(name="slice", fire_when="after_300",
                                     condition='extract($name, /(\\d+)/, 1.3) = "1"')],
                                     hooks=("before_300", "after_300"))
    eq([x.type for x in findings], ["rx_bad_condition"], "another hook's fire surfaces it - no crash")
    ok(deferred is None, "…and stays a no-op (the rule is after_300's business)")


def test_loop_schema_is_the_tables_declared_columns():
    """Refuter round 7 B2: the loop-column check read the schema off the ROWS, and a freshly staged
    row lacks the columns later phases fill (name_in_db, ...) - a real column failed at after_300 only.
    The engine's `_db` rows now carry every declared column (absent cells as "")."""
    def body(sandbox):
        with tempfile.TemporaryDirectory() as out_root:
            src = Table("src", columns=["uid", "kind", "name", "later_filled"], key_columns=["name"])
            src.add(kind="door", name="D1")                # NO row carries `later_filled`
            database = Database([src])
            rule = _rule(action="file", source_table="", condition="", target="cols.txt", template="txt")
            database, findings = engine.fire("after_300", database, rules=[rule],
                                             templates={"txt": "@for $r in src: [{$r.name}|{$r.later_filled}]"},
                                             params={}, files_root=out_root)
            eq(findings, [], "a declared-but-unfilled column is a real column")
            with open(os.path.join(out_root, "cols.txt"), encoding="utf-8") as handle:
                eq(handle.read(), "[D1|]\n", "…rendered blank")
            _, findings = engine.fire("after_300", database, rules=[rule],
                                      templates={"txt": "@for $r in src: [{$r.later_filed}]"},
                                      params={}, files_root=out_root)
            eq([x.type for x in findings], ["rx_bad_template"], "a misspelled column still fails")
    _sandboxed(body)()


def test_recording_appends_to_the_on_disk_record():
    """Refuter round 7 B3: the 310 leg stages a Database WITHOUT validation_issues; recording a
    reaction finding created an empty table and SAVED it over the file - wiping what an earlier
    phase recorded. A database that never loaded the record appends to the on-disk one (and the
    audit keeps the other hooks' rows), exactly like record_standalone."""
    from pipeline5.findings.finding import Finding, record_standalone
    def body(sandbox):
        prior = Finding(phase=110, type="probe_prior", severity="FAIL", detail="from phase 110", location="X1")
        record_standalone([prior], directory=sandbox)
        seed = Database([engine.chain_reactions_log_table()])
        seed[engine.LOG_TABLE].add(hook="after_500", rule="later", action="file", target="t",
                                   matches=1, created=1, outcome="ok")
        seed.save(sandbox)
        staged_310 = Database([Table("src", columns=["uid", "kind", "name"], key_columns=["name"])])
        staged_310, findings = engine.fire("after_300", staged_310, rules=[_rule(source_table="nope")],
                                           templates=_ROW_TPL, params={})
        from pipeline5.truth.database import Database as _Db
        from pipeline5.findings.finding import validation_issues_table
        on_disk = _Db([validation_issues_table(), engine.chain_reactions_log_table()]).load(sandbox)
        eq(sorted(r["type"] for r in on_disk["validation_issues"]), ["probe_prior", "rx_unknown_table"],
           "the earlier phase's record survived; the reaction finding was appended")
        eq(sorted((r["hook"], r["rule"]) for r in on_disk[engine.LOG_TABLE]),
           [("after_300", "r1"), ("after_500", "later")], "…and the other hook's audit row survived too")
    _sandboxed(body)()


def test_created_counts_survive_a_mid_action_failure():
    """Refuter round 7 B4: `created` was assigned only on a clean return, so a failure after some
    rows/lines were written audited created=0; and `{$n:03d}` on 'inf' leaked a raw OverflowError
    (filed as a code crash instead of a template finding)."""
    def body(sandbox):
        src = Table("src", columns=["uid", "n"], key_columns=["n"])
        for n in ("1", "2", "inf"):
            src.add(n=n)
        dst = Table("dst", columns=["uid", "label"], key_columns=["label"])
        database = Database([src, dst])
        database, findings = engine.fire("after_300", database, rules=[_rule(condition="")],
                                         templates={"rows": [{"label": "x{$n:03d}"}]}, params={})
        eq([x.type for x in findings], ["rx_bad_template"], "a data overflow is a TEMPLATE finding")
        eq([r["label"] for r in database["dst"]], ["x001", "x002"], "two rows were spawned before it")
        eq(_log(database), [("after_300", "r1", 3, 2, "rx_bad_template")], "…and the audit says so")
        # an UNFORESEEN defect mid-action (the backstop path) keeps the partial count as well
        with tempfile.TemporaryDirectory() as out_root:
            calls = {"n": 0}
            real = engine.tempemplator.render_template

            def flaky(*args, **kwargs):
                calls["n"] += 1
                if calls["n"] == 2:
                    raise RuntimeError("disk on fire")
                return real(*args, **kwargs)
            engine.tempemplator.render_template = flaky
            try:
                database, findings = engine.fire("after_300", _db(),
                                                 rules=[_rule(action="file", target="f.txt", template="txt")],
                                                 templates={"txt": "line {$name}"}, params={}, files_root=out_root)
            finally:
                engine.tempemplator.render_template = real
            eq([x.type for x in findings], ["rx_rule_crashed"])
            eq(_log(database), [("after_300", "r1", 2, 1, "rx_rule_crashed")],
               "the first match's line was written and is counted despite the crash")
    _sandboxed(body)()


def test_another_declared_hooks_malformed_rule_surfaces_without_writing():
    """Refuter round 7 E2: a malformed rule on ANOTHER declared hook must still surface here (it
    would otherwise stay silent whenever its own hook never fires - a halted staging) - while this
    rule-less hook stays a no-op that writes nothing (its own hook records it)."""
    def body(sandbox):
        database = _db()
        out, findings = engine.fire("after_300", database,
                                    rules=[_rule(name="m5", fire_when="after_500", action="explode")],
                                    templates=_ROW_TPL, params={}, hooks=("after_300", "after_500"))
        eq([(x.type, x.location) for x in findings], [("rx_bad_rule", "m5")], "it surfaces here")
        ok("validation_issues" not in database and engine.LOG_TABLE not in database, "nothing recorded here")
        eq(os.listdir(sandbox), [], "…nothing written")
    _sandboxed(body)()


def test_config_load_failures_block_on_the_default_path():
    """Refuter round 7 E3: the templates-block pin injected `params`, so the default path the
    run-plan uses was never tried: a params load must not run (and clobber the block) once the
    templates failed; and an unreadable params file is its own finding (rx_params_unreadable)."""
    def body(sandbox):
        def unreadable():
            raise ValueError("does not parse")
        saved = (config.load_reaction_templates, config.load_params)
        try:
            config.load_reaction_templates = unreadable
            config.load_params = lambda: (_ for _ in ()).throw(AssertionError("params must not load"))
            database, findings = engine.fire("after_300", _db(), rules=[_rule()])     # params left default
            eq([x.type for x in findings], ["rx_templates_unreadable"], "the templates block stands")
            eq([row[-1] for row in _log(database)], ["rx_templates_unreadable"])
            config.load_reaction_templates = lambda: dict(_ROW_TPL)
            config.load_params = unreadable
            database, findings = engine.fire("after_300", _db(), rules=[_rule()])
            eq([x.type for x in findings], ["rx_params_unreadable"], "an unreadable params file is a finding")
            eq([row[-1] for row in _log(database)], ["rx_params_unreadable"], "…blocking the hook's rules")
        finally:
            config.load_reaction_templates, config.load_params = saved
    _sandboxed(body)()


def test_matched_rows_carry_every_declared_column():
    """Refuter round 8 R2: only the `_db` rows were completed - a MATCHED row still lacked the
    columns staging leaves unfilled, so a top-level `{$later_filled}` failed (in the text, the row
    template and the target path) while the same column worked inside a loop."""
    def body(sandbox):
        with tempfile.TemporaryDirectory() as out_root:
            src = Table("src", columns=["uid", "kind", "name", "later_filled"], key_columns=["name"])
            src.add(kind="door", name="D1")                # NO row carries `later_filled`
            dst = Table("dst", columns=["uid", "label"], key_columns=["label"])
            database = Database([src, dst])
            file_rule = _rule(name="f", action="file", condition="", target="{$later_filled}top.txt", template="txt")
            rows_rule = _rule(name="r", condition="", template="rows")
            database, findings = engine.fire("after_300", database, rules=[file_rule, rows_rule],
                                             templates={"txt": "[{$name}|{$later_filled}]",
                                                        "rows": [{"label": "{$later_filled}x"}]},
                                             params={}, files_root=out_root)
            eq(findings, [], "a declared-but-unfilled column is a field of the matched row")
            with open(os.path.join(out_root, "top.txt"), encoding="utf-8") as handle:
                eq(handle.read(), "[D1|]\n", "…in the text AND the target path")
            eq([r["label"] for r in database["dst"]], ["x"], "…and in a row template")
    _sandboxed(body)()


def test_data_function_predicates_work_in_strict_holes():
    """Refuter round 8 R3: a predicate's `$col` is the ITERATED row's column, yet the strict hole
    check demanded it of the CURRENT row - a fire-once `{count(src, $kind = "door")}` failed."""
    def body(sandbox):
        with tempfile.TemporaryDirectory() as out_root:
            rule = _rule(action="file", source_table="", condition="", target="n.txt", template="txt")
            _, findings = engine.fire("after_300", _db(), rules=[rule],
                                      templates={"txt": 'doors={count(src, $kind = "door")}'},
                                      params={}, files_root=out_root)
            eq(findings, [], "the predicate's row column is not a missing field of the hole")
            with open(os.path.join(out_root, "n.txt"), encoding="utf-8") as handle:
                eq(handle.read(), "doors=2.0\n", "…and the count renders")
    _sandboxed(body)()


def test_a_record_that_cannot_load_or_save_is_a_finding():
    """Refuter round 8 R4: round 7's on-disk attach made a ragged hand-edited CSV crash fire()/settle()
    - and a file held open (Excel's deny-write) crashed the save. Both are located findings now; a
    record that does not load is NOT overwritten."""
    def body(sandbox):
        log_path = os.path.join(sandbox, f"{engine.LOG_TABLE}.csv")
        with open(log_path, "w", encoding="utf-8", newline="") as handle:
            handle.write("uid,hook,rule,action,target,matches,created,outcome\n"
                         "u1,after_500,x,file,t,1,1,ok,EXTRA-CELL\n")
        with open(log_path, "rb") as handle:
            before = handle.read()
        database, findings = engine.fire("after_300", _db(), rules=[_rule(source_table="nope")],
                                         templates=_ROW_TPL, params={})
        eq([x.type for x in findings], ["rx_unknown_table", "rx_record_unreadable"], "no crash - reported")
        with open(log_path, "rb") as handle:
            eq(handle.read(), before, "the ragged record was left untouched")
        deferred, _ = engine.fire("before_300", None, rules=[_rule(fire_when="before_300")],
                                  templates=_ROW_TPL, params={})
        eq([x.type for x in engine.settle(_db(), deferred)], ["rx_record_unreadable"], "settle reports it too")
        os.remove(log_path)
        locked = _db()

        def held_open(directory):
            raise PermissionError(13, "Permission denied", os.path.join(directory, "dst.csv"))
        locked.save = held_open
        _, findings = engine.fire("after_300", locked, rules=[_rule()], templates=_ROW_TPL, params={})
        eq([x.type for x in findings], ["rx_record_unwritable"], "a save that fails is a finding")
    _sandboxed(body)()


def test_file_level_findings_are_one_record_across_phases():
    """Refuter round 8 R5: an unreadable reactions.csv took the FIRING hook's phase, so a run-plan
    whose hooks span phases recorded it once per phase (different uids). File-level = phase 0."""
    def body(sandbox):
        def unreadable():
            raise UnicodeDecodeError("utf-8", b"\x92", 0, 1, "invalid start byte")
        original = config.load_reactions
        config.load_reactions = unreadable
        try:
            database, _ = engine.fire("before_300", _db())
            database, _ = engine.fire("after_500", database)
        finally:
            config.load_reactions = original
        eq([(r["type"], str(r["phase"])) for r in database["validation_issues"]], [("rx_rules_unreadable", "0")],
           "ONE record, phase 0, whichever hook met the broken file")
    _sandboxed(body)()


def test_recording_dedupes_within_one_fire_and_reads_extra_columns():
    """Refuter round 8 EH2/EH3: a rule row pasted twice fails twice with the SAME uid in one fire -
    recorded once; and a table's EXTRA (undeclared) column - e.g. a spawned row's `spawned_by` - is
    one of its columns for the loop schema."""
    def body(sandbox):
        database, findings = engine.fire("after_300", _db(), rules=[_rule(source_table="nope")] * 2,
                                         templates=_ROW_TPL, params={})
        eq(len(findings), 2, "both copies surface")
        eq([r["type"] for r in database["validation_issues"]], ["rx_unknown_table"], "…recorded ONCE")
        with tempfile.TemporaryDirectory() as out_root:
            dst = Table("dst", columns=["uid", "label"], key_columns=["label"])
            dst.add(label="L1", spawned_by="r0")          # an undeclared extra column
            rule = _rule(action="file", source_table="", condition="", target="x.txt", template="txt")
            _, findings = engine.fire("after_300", Database([dst]), rules=[rule],
                                      templates={"txt": "@for $r in dst: {$r.label} by {$r.spawned_by}"},
                                      params={}, files_root=out_root)
            eq(findings, [], "an extra column is a column")
            with open(os.path.join(out_root, "x.txt"), encoding="utf-8") as handle:
                eq(handle.read(), "L1 by r0\n")
    _sandboxed(body)()


def test_a_cascade_within_one_hook_sees_the_earlier_spawns():
    """Refuter round 9 (medium): `_db` was snapshotted ONCE per fire, while matching read the live
    table - a rule after an add_rows rule in the same hook counted/looped over a table WITHOUT the
    spawns (a silent wrong answer, audited `ok`), and even failed the schema of a spawned column.
    The chain reaction within one hook is the engine's core use: `_db` is rebuilt after a spawn."""
    def body(sandbox):
        with tempfile.TemporaryDirectory() as out_root:
            src = Table("src", columns=["uid", "kind", "name"], key_columns=["name"])
            src.add(kind="door", name="D1")
            src.add(kind="door", name="D2")
            dst = Table("dst", columns=["uid", "label"], key_columns=["label"])   # spawned_by NOT declared
            spawn = _rule(name="spawn", template="rows")
            read = _rule(name="read", action="file", source_table="", condition="", target="c.txt", template="txt")
            database, findings = engine.fire("after_300", Database([src, dst]), rules=[spawn, read],
                                             templates={"rows": [{"label": "spawn-{$name}"}],
                                                        "txt": "n={count(dst, present($spawned_by))}\n"
                                                               "@for $d in dst: {$d.label} by {$d.spawned_by}"},
                                             params={}, files_root=out_root)
            eq(findings, [], "the later rule sees the spawned column")
            with open(os.path.join(out_root, "c.txt"), encoding="utf-8") as handle:
                eq(handle.read(), "n=2.0\nspawn-D1 by spawn\nspawn-D2 by spawn\n",
                   "…and the spawned ROWS - count and loop alike")
    _sandboxed(body)()


def test_record_attaches_atomically_and_spawns_survive_a_ragged_record():
    """Refuter round 9: (a) a ragged validation_issues.csv (the 310 leg - the database never loaded
    it) is the same rx_record_unreadable, bytes untouched, NEITHER record table attached (a half-
    attached one would be saved); (b) with a ragged audit, the engine used to skip the WHOLE save -
    an add_rows spawn silently vanished while the run reported it. The rest of the Database is saved."""
    def body(sandbox):
        ragged_issues = os.path.join(sandbox, "validation_issues.csv")
        with open(ragged_issues, "w", encoding="utf-8", newline="") as handle:
            handle.write("uid,id,phase,type\nu1,1,110,x,EXTRA-CELL\n")
        with open(ragged_issues, "rb") as handle:
            before = handle.read()
        staged_310 = Database([Table("src", columns=["uid", "kind", "name"], key_columns=["name"])])
        _, findings = engine.fire("after_300", staged_310, rules=[_rule(source_table="nope")],
                                  templates=_ROW_TPL, params={})
        eq([x.type for x in findings], ["rx_unknown_table", "rx_record_unreadable"], "no crash - reported")
        with open(ragged_issues, "rb") as handle:
            eq(handle.read(), before, "the ragged findings record is untouched")
        ok(not os.path.exists(os.path.join(sandbox, f"{engine.LOG_TABLE}.csv")),
           "the audit was NOT half-attached (it would have been saved)")
        os.remove(ragged_issues)
        with open(os.path.join(sandbox, f"{engine.LOG_TABLE}.csv"), "w", encoding="utf-8", newline="") as handle:
            handle.write("uid,hook,rule,action,target,matches,created,outcome\nu1,after_500,x,f,t,1,1,ok,EXTRA\n")
        database, findings = engine.fire("after_300", _db(), rules=[_rule()], templates=_ROW_TPL, params={})
        eq([x.type for x in findings], ["rx_record_unreadable"])
        ok("the rest of the Database was saved" in findings[0].detail, "the finding says what WAS kept")
        from pipeline5.truth.database import Database as _Db
        saved = _Db([Table("dst", columns=["uid", "label", "spawned_by", "source_uid"], key_columns=["label"])]).load(sandbox)
        eq(sorted(r["label"] for r in saved["dst"]), ["spawn-D1", "spawn-D2"], "the spawns were SAVED")
    _sandboxed(body)()


def test_a_condition_failing_at_evaluation_is_a_bad_condition():
    """Refuter round 9: every rx_bad_condition pin failed at COMPILE; a condition that compiles but
    raises a located ExprError when EVALUATED (a bad group reference) must still be rx_bad_condition,
    never relabelled rx_rule_crashed (a different audit outcome and treatment uid)."""
    def body(sandbox):
        database, findings = engine.fire("after_300", _db(),
                                         rules=[_rule(condition='regex_replace($name, /(D)/, "\\\\9") = "x"')],
                                         templates=_ROW_TPL, params={})
        eq([x.type for x in findings], ["rx_bad_condition"], "an evaluation-time ExprError")
        eq(_log(database), [("after_300", "r1", 0, 0, "rx_bad_condition")])
    _sandboxed(body)()


def test_round_10_evidence_holes():
    """Refuter round 10's evidence holes (the code held; nothing pinned it):
    (a) a FILE rule naming a ROW template is rx_bad_template BEFORE any matching - with zero matches
        the renderer never runs, so only the pre-check catches it (round 6's B4 class);
    (b) `_db` is rebuilt after a PARTIALLY failed spawn too - the rows it did create are real;
    (c) record load/save failures of OTHER exception classes (a directory where the CSV should be; a
        full disk) are the same located findings - never a crash."""
    import errno
    def body(sandbox):
        with tempfile.TemporaryDirectory() as out_root:
            _, findings = engine.fire("after_300", _db(),
                                      rules=[_rule(action="file", condition='$kind = "none"', target="x.txt")],
                                      templates=_ROW_TPL, params={}, files_root=out_root)
            eq([x.type for x in findings], ["rx_bad_template"], "(a) wrong kind caught with zero matches")
            src = Table("src", columns=["uid", "n"], key_columns=["n"])
            for n in ("1", "2", "inf"):
                src.add(n=n)
            dst = Table("dst", columns=["uid", "label"], key_columns=["label"])
            spawn = _rule(name="spawn", condition="", template="rows")
            read = _rule(name="read", action="file", source_table="", condition="", target="c.txt", template="txt")
            _, findings = engine.fire("after_300", Database([src, dst]), rules=[spawn, read],
                                      templates={"rows": [{"label": "x{$n:03d}"}], "txt": "{count(dst)}"},
                                      params={}, files_root=out_root)
            eq([x.type for x in findings], ["rx_bad_template"], "(b) the spawn failed on 'inf'…")
            with open(os.path.join(out_root, "c.txt"), encoding="utf-8") as handle:
                eq(handle.read(), "2.0\n", "…yet the later rule saw the TWO rows it created")
        issues_path = os.path.join(sandbox, "validation_issues.csv")
        if os.path.exists(issues_path):
            os.remove(issues_path)                                         # (the earlier fires saved one)
        os.mkdir(issues_path)                                              # (c) an OSError on READ
        _, findings = engine.fire("after_300", Database([Table("src", columns=["uid"], key_columns=["uid"])]),
                                  rules=[_rule(source_table="nope")], templates=_ROW_TPL, params={})
        eq([x.type for x in findings], ["rx_unknown_table", "rx_record_unreadable"], "(c) unreadable: a directory")
        os.rmdir(os.path.join(sandbox, "validation_issues.csv"))
        full = _db()

        def disk_full(directory):
            raise OSError(errno.ENOSPC, "No space left on device")
        full.save = disk_full
        _, findings = engine.fire("after_300", full, rules=[_rule()], templates=_ROW_TPL, params={})
        eq([x.type for x in findings], ["rx_record_unwritable"], "(c) unwritable: a full disk")
    _sandboxed(body)()


def test_round_12_target_strictness_and_else_if():
    """Refuter round 12: (a) the FILE TARGET's strict render was unpinned - rendered leniently, a typo'd
    `gen/{$nmae}.txt` appended every belt into `gen/.txt`, audited ok; (b) a template using `@else if`
    rendered the wrong branch for every row, audited ok - now a template finding, nothing written."""
    def body(sandbox):
        with tempfile.TemporaryDirectory() as out_root:
            _, findings = engine.fire("after_300", _db(),
                                      rules=[_rule(action="file", target="gen/{$nmae}.txt", template="txt")],
                                      templates={"txt": "x"}, params={}, files_root=out_root)
            eq([x.type for x in findings], ["rx_bad_template"], "(a) a typo'd target field")
            eq(os.listdir(out_root), [], "…and NOTHING was written")
            database, findings = engine.fire("after_300", _db(),
                                             rules=[_rule(action="file", target="m.txt", template="txt")],
                                             templates={"txt": '@if $name = "D1"\nONE\n@else if $name = "D2"\nTWO\n@end'},
                                             params={}, files_root=out_root)
            eq([x.type for x in findings], ["rx_bad_template"], "(b) `@else if` is a finding, not a wrong branch")
            ok(not os.path.exists(os.path.join(out_root, "m.txt")), "…and nothing was written")
    _sandboxed(body)()


def test_undeclared_hooks_malformed_rule_is_recorded_by_a_rule_less_hook():
    """U3 (the orchestrator's mutation check): a malformed rule on a hook the run-plan never fires can
    never be recorded at its own hook - so it is an INDEX problem, recorded even by a hook that has no
    rule of its own. (Its own sandbox: an earlier record on disk would mask the case.)"""
    def body(sandbox):
        lone, findings = engine.fire("after_300", _db(),
                                     rules=[_rule(name="mal", fire_when="after_520", action="explode")],
                                     templates=_ROW_TPL, params={}, hooks=("before_300", "after_300"))
        eq([x.type for x in findings], ["rx_bad_rule"])
        eq([r["type"] for r in lone["validation_issues"]], ["rx_bad_rule"],
           "recorded although this hook has no rules - it can never be recorded at its own (unfired) hook")
    _sandboxed(body)()


def test_unreadable_rules_file_is_recorded_not_just_rendered():
    """Round-6 implications: an unreadable reactions.csv (e.g. an Excel cp1252 save) was rendered
    at both hooks but never recorded or audited. It is every hook's business now: the database-less
    hook DEFERS it, the staged one persists it - recorded once."""
    def body(sandbox):
        def unreadable():
            raise UnicodeDecodeError("utf-8", b"\x92", 0, 1, "invalid start byte")
        original = config.load_reactions
        config.load_reactions = unreadable
        try:
            deferred, f1 = engine.fire("before_300", None)
            database, f2 = engine.fire("after_300", _db())
        finally:
            config.load_reactions = original
        eq([x.type for x in f1], ["rx_rules_unreadable"], "the before-hook reports it")
        ok(isinstance(deferred, engine.Deferred) and deferred.findings == f1, "…and DEFERS it")
        eq([x.type for x in f2], ["rx_rules_unreadable"], "the after-hook reports it")
        engine.settle(database, deferred)
        eq([r["type"] for r in database["validation_issues"]], ["rx_rules_unreadable"],
           "recorded ONCE across both hooks (uid dedupe)")
    _sandboxed(body)()


def test_noop_loads_nothing_beyond_the_rule_index():
    """E2 (refuter round 6): 'nothing further loads' on a rule-less hook - with the templates /
    params / output-root loaders all RAISING, a hook with no rules (the index read through the REAL
    load_reactions seam) must return clean. Moving the early return below the loads dies here."""
    def boom(*_a, **_k):
        raise AssertionError("a rule-less hook must not load this")
    saved = (config.load_reactions, config.load_reaction_templates, config.load_params, config.output_root)
    config.load_reactions = lambda: [_rule(fire_when="after_500")]           # rules, but not this hook's
    config.load_reaction_templates = config.load_params = config.output_root = boom
    try:
        database = _db()
        out, findings = engine.fire("after_300", database)                   # every default -> loaders
        ok(out is database and findings == [], "the rule-less hook returned without loading")
        ok(engine.LOG_TABLE not in database, "…and logged nothing")
    finally:
        (config.load_reactions, config.load_reaction_templates, config.load_params,
         config.output_root) = saved


def test_add_rows_spawns_with_provenance():
    def body(sandbox):
        database = _db()
        database, findings = engine.fire("after_300", database, rules=[_rule()],
                                         templates=_ROW_TPL, params={})
        eq(findings, [], "a clean rule emits no findings")
        spawned = list(database["dst"])
        eq([r["label"] for r in spawned], ["spawn-D1", "spawn-D2"],
           "one row per matched source row, expr-filled ($kind = door only)")
        src_uids = {r["name"]: r["uid"] for r in database["src"]}
        eq([r["spawned_by"] for r in spawned], ["r1", "r1"], "provenance: the rule name")
        eq([r["source_uid"] for r in spawned], [src_uids["D1"], src_uids["D2"]],
           "provenance: the triggering row's uid")
        ok(all(r.get("uid") for r in spawned), "spawned rows are uid-stamped by the target table")
        eq(_log(database), [("after_300", "r1", 2, 2, "ok")],
           "the audit row: hook, rule, match count, rows created, outcome")
        ok(os.path.exists(os.path.join(sandbox, "dst.csv")), "the database was SAVED")
        ok(os.path.exists(os.path.join(sandbox, f"{engine.LOG_TABLE}.csv")), "the log persisted")
    _sandboxed(body)()


def test_multi_spec_row_template_and_log_replacement():
    def body(sandbox):
        database = _db()
        tpl = {"rows": [{"label": "a-{$name}"}, {"label": "b-{$name}"}]}
        database, _ = engine.fire("after_300", database, rules=[_rule()], templates=tpl, params={})
        eq(len(database["dst"]), 4, "2 row-specs x 2 matches = 4 spawned rows")
        eq(list(database[engine.LOG_TABLE])[0]["created"], 4)
        # a re-fire REPLACES this hook's audit rows (the log reflects THE LAST run, never accumulates)
        database, _ = engine.fire("after_300", database, rules=[_rule()], templates=tpl, params={})
        eq(len(list(database[engine.LOG_TABLE])), 1, "one audit row per rule after a re-fire")
        eq(len(database["dst"]), 8, "spawning itself DID append again (idempotency is the rule author's contract)")
    _sandboxed(body)()


def test_failures_are_located_findings():
    def body(sandbox):
        database = _db()
        # unknown source table -> skipped, AUDITED with its outcome, RECORDED on its own (B2: the
        # record used to depend on some sibling rule having produced a log row)
        database, f1 = engine.fire("after_300", database, rules=[_rule(source_table="nope")],
                                   templates=_ROW_TPL, params={})
        eq([x.type for x in f1], ["rx_unknown_table"])
        eq(_log(database), [("after_300", "r1", 0, 0, "rx_unknown_table")],
           "a rule that could not read its source is audited with that outcome")
        eq([r["uid"] for r in database["validation_issues"]], [f1[0].uid],
           "the match-stage failure itself landed in validation_issues")
        with open(os.path.join(sandbox, "validation_issues.csv"), encoding="utf-8") as handle:
            ok("rx_unknown_table" in handle.read(), "…and on disk (the Findings panel reads the file)")
        # unknown target table -> fired, audited with created=0, finding
        database, f2 = engine.fire("after_300", database, rules=[_rule(target="nope")],
                                   templates=_ROW_TPL, params={})
        eq([x.type for x in f2], ["rx_unknown_table"])
        eq(_log(database), [("after_300", "r1", 2, 0, "rx_unknown_table")])
        # a condition typo is caught at COMPILE, even over an EMPTY source table (B4b)
        empty = Database([Table("src", columns=["uid", "kind", "name"], key_columns=["name"]),
                          Table("dst", columns=["uid", "label"], key_columns=["label"])])
        empty, f3 = engine.fire("after_300", empty, rules=[_rule(condition="let(")],
                                templates=_ROW_TPL, params={})
        eq([x.type for x in f3], ["rx_bad_condition"])
        eq([r["type"] for r in empty["validation_issues"]], ["rx_unknown_table", "rx_unknown_table", "rx_bad_condition"],
           "the hook OWNS its malformed rule, so the finding is recorded - APPENDED to the on-disk record "
           "this fresh database never loaded (the earlier fires' findings survive: refuter round 7 B3)")
        # text-template-for-add_rows / bad field expr / a file rule naming a MISSING template
        # (caught before matching - B4b: nothing matched, and it was silent)
        _, f4 = engine.fire("after_300", _db(), rules=[_rule()],
                            templates={"rows": "I am text"}, params={})
        eq([x.type for x in f4], ["rx_bad_template"])
        _, f5 = engine.fire("after_300", _db(), rules=[_rule()],
                            templates={"rows": [{"label": "{$missing_field}"}]}, params={})
        eq([x.type for x in f5], ["rx_bad_template"])
        _, f6 = engine.fire("after_300", _db(), rules=[_rule(action="file", condition='$kind = "none"',
                                                             target="x.txt", template="nope")],
                            templates={}, params={}, files_root=sandbox)
        eq([x.type for x in f6], ["rx_bad_template"], "a missing template is caught with zero matches")
        ok(all(x.severity == "ERRR" for x in f1 + f2 + f3 + f4 + f5 + f6), "every failure is ERRR")
    _sandboxed(body)()


def test_malformed_row_templates_are_findings_not_crashes():
    """B1 (refuter round 6): row templates that are not a non-empty list of {field: value} maps
    raised ValueError / TypeError out of fire(). Each is a located rx_bad_template now."""
    def body(sandbox):
        for label, spec in (("a list of strings", ["label"]), ("a null entry", [None]),
                            ("an empty list", []), ("an empty map", [{}]),
                            ("a null field value", [{"label": None}]),
                            # YAML-typed values used to be COERCED silently (a list stored as its repr,
                            # 007 as 7, true as True) - refuter round 9: every value is a template STRING
                            ("a list value", [{"label": ["a", "b"]}]), ("an int value", [{"label": 7}]),
                            ("a bool value", [{"label": True}])):
            database, findings = engine.fire("after_300", _db(), rules=[_rule()],
                                             templates={"rows": spec}, params={})
            eq([(x.type, x.location) for x in findings], [("rx_bad_template", "r1")], label)
            eq(len(database["dst"]), 0, f"{label}: nothing spawned")
    _sandboxed(body)()


def test_raw_exceptions_become_findings():
    """B1 (refuter round 6): every input that used to raise a RAW exception out of fire() - and so
    crashed the staging handler - is a located ERRR finding now; the run continues."""
    def body(sandbox):
        with tempfile.TemporaryDirectory() as out_root:
            # a rendered target the OS refuses (a path THROUGH an existing file - portable)
            with open(os.path.join(out_root, "blocker"), "w", encoding="utf-8") as handle:
                handle.write("x")
            rule = _rule(action="file", target="blocker/{$name}.txt", template="txt")
            _, findings = engine.fire("after_300", _db(), rules=[rule], templates={"txt": "t"},
                                      params={}, files_root=out_root)
            eq([x.type for x in findings], ["rx_file_write"], "an unwritable target is rx_file_write")
            if os.name == "nt":                          # the refuter's case: a quoted Siemens tag
                rule = _rule(action="file", target='rx/"{$name}".scl', template="txt")
                _, findings = engine.fire("after_300", _db(), rules=[rule], templates={"txt": "t"},
                                          params={}, files_root=out_root)
                eq([x.type for x in findings], ["rx_file_write"], "a `\"` in a Windows path")
            # a non-finite @for end inside the rendered template (OverflowError before)
            rule = _rule(action="file", target="loop.txt", template="txt")
            _, findings = engine.fire("after_300", _db(), rules=[rule],
                                      templates={"txt": "@for $i in 1..{$_params.n}: x"},
                                      params={"n": "inf"}, files_root=out_root)
            eq([x.type for x in findings], ["rx_bad_template"], "@for 1..inf is a template error")
            ok("finite" in findings[0].detail, "…the non-finite end, not some other failure")
            # the backstop: an UNFORESEEN defect inside the per-rule path (injected at the match seam)
            def defect(*_a, **_k):
                raise RuntimeError("disk on fire")
            real_matches, engine._matches = engine._matches, defect
            try:
                database, findings = engine.fire("after_300", _db(), rules=[_rule(), _rule(name="r2")],
                                                 templates=_ROW_TPL, params={})
            finally:
                engine._matches = real_matches
            eq([(x.type, x.location) for x in findings], [("rx_rule_crashed", "r1"), ("rx_rule_crashed", "r2")],
               "the backstop turns an unforeseen exception into a finding - per rule, the run continues")
            ok("RuntimeError" in findings[0].detail, "…naming the exception type")
            eq(_log(database), [("after_300", "r1", 0, 0, "rx_rule_crashed"),
                                ("after_300", "r2", 0, 0, "rx_rule_crashed")], "…and audits each")
    _sandboxed(body)()


def test_unloadable_templates_block_the_hook_without_crashing():
    """B1 (refuter round 6): a templates.yaml plain value starting with `@` (YAML-reserved - the
    renderer's own directive sigil) raised ruamel's ScannerError out of fire(). The REAL YAML
    reader is driven on a real file here: one rx_templates_unreadable finding, every active rule
    audited as blocked, the database still saved."""
    def body(sandbox):
        path = os.path.join(sandbox, "templates.yaml")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("OneLiner: @use other\n")
        original = config.load_reaction_templates
        config.load_reaction_templates = lambda: p5params._read_yaml(path)
        try:
            database, findings = engine.fire("after_300", _db(), rules=[_rule(), _rule(name="r2")],
                                             params={})
        finally:
            config.load_reaction_templates = original
        eq([x.type for x in findings], ["rx_templates_unreadable"], "one located finding, no crash")
        eq([row[-1] for row in _log(database)], ["rx_templates_unreadable"] * 2,
           "both active rules audited as blocked")
        eq(len(database["dst"]), 0, "nothing ran")
    _sandboxed(body)()


def test_failed_refire_replaces_the_previous_success():
    """B3 (refuter round 6): a re-fire whose rule FAILS used to leave the previous run's success
    row in the audit (the replacement only ran when rows were produced). Success -> failure ->
    malformed: the log always shows THE LAST run - saved to disk too."""
    def body(sandbox):
        database = _db()
        database, _ = engine.fire("after_300", database, rules=[_rule()], templates=_ROW_TPL, params={})
        eq(_log(database), [("after_300", "r1", 2, 2, "ok")], "run 1 succeeded")
        database, _ = engine.fire("after_300", database, rules=[_rule(source_table="gone")],
                                  templates=_ROW_TPL, params={})
        eq(_log(database), [("after_300", "r1", 0, 0, "rx_unknown_table")],
           "run 2 failed - its outcome REPLACED run 1's success row")
        with open(os.path.join(sandbox, f"{engine.LOG_TABLE}.csv"), encoding="utf-8") as handle:
            text = handle.read()
        ok("rx_unknown_table" in text and ",ok" not in text, "…in the saved file the Explorer loads")
        database, findings = engine.fire("after_300", database, rules=[_rule(action="explode")],
                                         templates=_ROW_TPL, params={})
        eq([x.type for x in findings], ["rx_bad_rule"])
        eq(_log(database), [], "run 3's only rule is malformed: nothing fired, the stale row is gone")
        # the record keeps ONE row per distinct finding however often it re-surfaces (uid dedupe)
        engine.fire("after_300", database, rules=[_rule(action="explode")], templates=_ROW_TPL, params={})
        eq([r["type"] for r in database["validation_issues"]].count("rx_bad_rule"), 1,
           "a re-surfacing finding is recorded once")
    _sandboxed(body)()


def test_file_action_appends_per_match():
    def body(sandbox):
        with tempfile.TemporaryDirectory() as out_root:
            database = _db()
            rule = _rule(action="file", target="gen/{$_rule.name}.scl", template="txt")
            tpl = {"txt": "// {$name}\ncall({$name});"}
            database, findings = engine.fire("after_300", database, rules=[rule],
                                             templates=tpl, params={}, files_root=out_root)
            eq(findings, [], "clean file rule")
            path = os.path.join(out_root, "gen", "r1.scl")
            ok(os.path.exists(path), "a relative target lands under files_root, expr-rendered")
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
            eq(text, "// D1\ncall(D1);\n// D2\ncall(D2);\n",
               "one rendered block APPENDED per matched row, newline-terminated")
            engine.fire("after_300", database, rules=[rule], templates=tpl, params={},
                        files_root=out_root)
            with open(path, encoding="utf-8") as handle:
                eq(handle.read().count("// D1"), 2,
                   "a re-fire APPENDS again - append is the only mode, lifecycle is the author's")
            eq(list(database[engine.LOG_TABLE])[0]["created"], 4, "line count audited")
    _sandboxed(body)()


def test_engine_builds_the_full_e1_scope():
    """The E1 scope AS THE ENGINE PRODUCES it (refuter round 3: the `db_tables = {}` mutant): a
    file rule whose template queries a DIFFERENT SSOT table through `_db` and drills `_params`
    dotted - fired end-to-end through the engine, not with a hand-passed scope. Also pins the audit
    row's `action`/`target` columns (the two the clause enumerates that no other test read)."""
    def body(sandbox):
        with tempfile.TemporaryDirectory() as out_root:
            src = Table("src", columns=["uid", "kind", "name"], key_columns=["name"])
            src.add(kind="door", name="D1")
            other = Table("other", columns=["uid", "name"], key_columns=["name"])
            other.add(name="X1")
            other.add(name="X2")
            database = Database([src, other])
            rule = _rule(action="file", target="gen/scope.txt", template="txt")
            tpl = {"txt": "[{$_params.project.name}] {$_rule.hook} for {$name}\n"
                          "@for $r in other: cross-{$r.name}"}
            database, findings = engine.fire("after_300", database, rules=[rule], templates=tpl,
                                             params={"project": {"name": "P1"}}, files_root=out_root)
            eq(findings, [], "the cross-table template renders clean through the engine")
            with open(os.path.join(out_root, "gen", "scope.txt"), encoding="utf-8") as handle:
                eq(handle.read(), "[P1] after_300 for D1\ncross-X1\ncross-X2\n",
                   "_params drilled dotted, _rule.hook resolved, AND _db reached the OTHER table - "
                   "every enumerated E1 layer built by the engine")
            log = list(database[engine.LOG_TABLE])[0]
            eq((log["action"], log["target"]), ("file", "gen/scope.txt"),
               "the audit row carries the action + raw target")
            # B5 through the engine: a misspelled COLUMN of a table-loop row is a finding, not a blank
            _, findings = engine.fire("after_300", database, rules=[rule],
                                      templates={"txt": "@for $r in other: cross-{$r.nmae}"},
                                      params={}, files_root=out_root)
            eq([x.type for x in findings], ["rx_bad_template"], "a loop-row column typo is caught")
    _sandboxed(body)()


def test_sourceless_and_before_hook_semantics():
    def body(sandbox):
        with tempfile.TemporaryDirectory() as out_root:
            # a source-less file rule fires ONCE (e.g. a generated-file header), even with NO database;
            # the database-less hook returns its trail DEFERRED (nothing can be persisted yet)
            rule = _rule(name="hdr", fire_when="before_300", source_table="", condition="",
                         action="file", target="gen/out.txt", template="txt")
            deferred, findings = engine.fire("before_300", None, rules=[rule],
                                             templates={"txt": "HEADER"}, params={}, files_root=out_root)
            eq(findings, [], "a before-hook file rule needs no database")
            ok(isinstance(deferred, engine.Deferred), "the database-less hook DEFERS its trail")
            eq([(r["rule"], r["matches"], r["created"], r["outcome"]) for r in deferred.log_rows],
               [("hdr", 1, 1, "ok")], "…the audit row travels in the Deferred")
            with open(os.path.join(out_root, "gen", "out.txt"), encoding="utf-8") as handle:
                eq(handle.read(), "HEADER\n")
            # add_rows at a database-less hook -> a pointed finding, never a crash
            deferred2, f = engine.fire("before_300", None,
                                       rules=[_rule(fire_when="before_300")], templates=_ROW_TPL, params={})
            eq([x.type for x in f], ["rx_unknown_table"])
            eq(deferred2.findings, f, "the finding travels in the Deferred too")
            # settle: once a database exists, the deferred audit + findings land in it (B2 for
            # before-hooks: they used to be rendered and then lost)
            database = _db()
            engine.settle(database, deferred2)
            eq(_log(database), [("before_300", "r1", 0, 0, "rx_unknown_table")], "settled audit")
            eq([r["type"] for r in database["validation_issues"]], ["rx_unknown_table"], "settled record")
            ok(os.path.exists(os.path.join(sandbox, "validation_issues.csv")), "…saved")
            # a rule-less before-hook returns None - and settling None is a strict no-op
            none, _ = engine.fire("before_300", None, rules=[], templates={}, params={})
            ok(none is None, "no rules -> nothing deferred")
            fresh = _db()
            engine.settle(fresh, None)
            ok(engine.LOG_TABLE not in fresh and "validation_issues" not in fresh, "settle(None) touches nothing")
    _sandboxed(body)()


def test_rules_fire_in_csv_order_and_only_their_hook():
    def body(sandbox):
        database = _db()
        rules = [_rule(name="second", template="rows"),
                 _rule(name="first", template="rows"),
                 _rule(name="other-hook", fire_when="after_500")]
        database, _ = engine.fire("after_300", database, rules=rules, templates=_ROW_TPL, params={})
        log = [r["rule"] for r in database[engine.LOG_TABLE]]
        eq(log, ["second", "first"], "CSV order is the firing order; other hooks stay cold")
        # the replacement is PER HOOK (refuter round 4: the clobber-all mutant `log.rows = []`):
        # firing ANOTHER hook must keep this hook's audit rows - the Run-all scenario where every
        # phase's fire would otherwise wipe the previous phase's trail
        database, _ = engine.fire("after_500", database, rules=rules, templates=_ROW_TPL, params={})
        by_hook = sorted((r["hook"], r["rule"]) for r in database[engine.LOG_TABLE])
        eq(by_hook, [("after_300", "first"), ("after_300", "second"), ("after_500", "other-hook")],
           "the after_500 fire replaced ONLY its own hook's rows; after_300's audit survives")
        database, _ = engine.fire("after_500", database, rules=rules, templates=_ROW_TPL, params={})
        eq(len(list(database[engine.LOG_TABLE])), 3, "a re-fire still replaces, never accumulates")
    _sandboxed(body)()


def test_builtin_config_ships_empty_rules():
    """The Siemens builtin ships the config PAIR with ZERO active rules (the engine lands dark -
    the plan's parity guarantee) while the reference templates exist for authors."""
    eq(config.load_reactions(), [], "no builtin rules")
    ok(len(config.load_reaction_templates()) >= 3, "the worked-example templates ship")


if __name__ == "__main__":
    import sys
    sys.exit(run("chain_reactions", [
        ("compile_validates_and_drops_bad_rows", test_compile_validates_and_drops_bad_rows),
        ("unnamed_and_uncompilable_rules_are_caught_at_compile",
         test_unnamed_and_uncompilable_rules_are_caught_at_compile),
        ("loader_passes_nameless_rows_to_the_compiler", test_loader_passes_nameless_rows_to_the_compiler),
        ("fire_empty_hook_is_a_strict_noop", test_fire_empty_hook_is_a_strict_noop),
        ("noop_loads_nothing_beyond_the_rule_index", test_noop_loads_nothing_beyond_the_rule_index),
        ("rules_on_hooks_the_run_plan_never_fires_are_reported",
         test_rules_on_hooks_the_run_plan_never_fires_are_reported),
        ("compile_never_crashes_a_hook", test_compile_never_crashes_a_hook),
        ("loop_schema_is_the_tables_declared_columns", test_loop_schema_is_the_tables_declared_columns),
        ("recording_appends_to_the_on_disk_record", test_recording_appends_to_the_on_disk_record),
        ("created_counts_survive_a_mid_action_failure", test_created_counts_survive_a_mid_action_failure),
        ("another_declared_hooks_malformed_rule_surfaces_without_writing",
         test_another_declared_hooks_malformed_rule_surfaces_without_writing),
        ("config_load_failures_block_on_the_default_path", test_config_load_failures_block_on_the_default_path),
        ("matched_rows_carry_every_declared_column", test_matched_rows_carry_every_declared_column),
        ("data_function_predicates_work_in_strict_holes", test_data_function_predicates_work_in_strict_holes),
        ("a_record_that_cannot_load_or_save_is_a_finding", test_a_record_that_cannot_load_or_save_is_a_finding),
        ("file_level_findings_are_one_record_across_phases", test_file_level_findings_are_one_record_across_phases),
        ("recording_dedupes_within_one_fire_and_reads_extra_columns",
         test_recording_dedupes_within_one_fire_and_reads_extra_columns),
        ("a_cascade_within_one_hook_sees_the_earlier_spawns", test_a_cascade_within_one_hook_sees_the_earlier_spawns),
        ("record_attaches_atomically_and_spawns_survive_a_ragged_record",
         test_record_attaches_atomically_and_spawns_survive_a_ragged_record),
        ("a_condition_failing_at_evaluation_is_a_bad_condition", test_a_condition_failing_at_evaluation_is_a_bad_condition),
        ("round_10_evidence_holes", test_round_10_evidence_holes),
        ("round_12_target_strictness_and_else_if", test_round_12_target_strictness_and_else_if),
        ("undeclared_hooks_malformed_rule_is_recorded_by_a_rule_less_hook",
         test_undeclared_hooks_malformed_rule_is_recorded_by_a_rule_less_hook),
        ("unreadable_rules_file_is_recorded_not_just_rendered",
         test_unreadable_rules_file_is_recorded_not_just_rendered),
        ("add_rows_spawns_with_provenance", test_add_rows_spawns_with_provenance),
        ("multi_spec_row_template_and_log_replacement", test_multi_spec_row_template_and_log_replacement),
        ("failures_are_located_findings", test_failures_are_located_findings),
        ("malformed_row_templates_are_findings_not_crashes", test_malformed_row_templates_are_findings_not_crashes),
        ("raw_exceptions_become_findings", test_raw_exceptions_become_findings),
        ("unloadable_templates_block_the_hook_without_crashing",
         test_unloadable_templates_block_the_hook_without_crashing),
        ("failed_refire_replaces_the_previous_success", test_failed_refire_replaces_the_previous_success),
        ("file_action_appends_per_match", test_file_action_appends_per_match),
        ("engine_builds_the_full_e1_scope", test_engine_builds_the_full_e1_scope),
        ("sourceless_and_before_hook_semantics", test_sourceless_and_before_hook_semantics),
        ("rules_fire_in_csv_order_and_only_their_hook", test_rules_fire_in_csv_order_and_only_their_hook),
        ("builtin_config_ships_empty_rules", test_builtin_config_ships_empty_rules),
    ]))
