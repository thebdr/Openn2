"""The chain-reaction engine (phases/chain_reactions/engine.py) - rule compilation, the fire()
lifecycle (match -> spawn/append -> audit log -> save), provenance, the strict empty-hook no-op,
and every failure surfacing as a located ERRR finding. Hermetic: synthetic tables + injected
rules/templates; the database dir is sandboxed."""
import os
import tempfile

from _harness import run, eq, ok
from pipeline5 import config
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


def test_compile_validates_and_drops_bad_rows():
    rules, findings = engine.compile_rules([
        _rule(),
        _rule(name="bad1", fire_when="sometime"),
        _rule(name="bad2", action="explode"),
        _rule(name="bad3", target=""),
        _rule(name="bad4", template=""),
        {"name": "", "fire_when": "after_300"},                      # blank name rows never arrive (loader)
    ])
    eq([r.name for r in rules], ["r1"], "only the valid rule compiles")
    eq(rules[0].phase, 300, "the hook's phase number is derived")
    bad = [f for f in findings if f.type == "rx_bad_rule"]
    eq(sorted(f.location for f in bad), ["<unnamed rule>", "bad1", "bad2", "bad3", "bad4"],
       "each malformed row is a located finding (a nameless one still locates)")
    ok(all(f.severity == "ERRR" for f in findings), "rule failures are ERRR (skip + continue)")


def test_fire_empty_hook_is_a_strict_noop(sandbox=None):
    def body(sandbox):
        database = _db()
        out, findings = engine.fire("after_300", database, rules=[], templates={}, params={})
        ok(out is database and findings == [], "no rules -> the same database, no findings")
        ok(engine.LOG_TABLE not in database, "no log table materialized")
        eq(os.listdir(sandbox), [], "NOTHING was written to disk (the byte-parity guarantee)")
        # the never-silent guarantee ON the fast path: a malformed rule (hook unparseable, so it
        # can never activate anywhere) still SURFACES through a rule-less fire (refuter round 2:
        # the drop-the-findings mutant `return database, []` dies here)
        out, findings = engine.fire("after_300", database,
                                    rules=[_rule(name="mal", fire_when="whenever"),
                                           _rule(name="cold", fire_when="after_500")],
                                    templates={}, params={})
        eq([(x.type, x.location) for x in findings], [("rx_bad_rule", "mal")],
           "the compile finding propagates even when this hook fires nothing")
        ok(engine.LOG_TABLE not in database, "…while still a no-op")
        eq(os.listdir(sandbox), [], "…that writes nothing")
    _sandboxed(body)()


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
        log = list(database[engine.LOG_TABLE])
        eq([(r["hook"], r["rule"], r["matches"], r["created"]) for r in log],
           [("after_300", "r1", 2, 1 * 2)], "the audit row: hook, rule, match count, rows created")
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
        # unknown source table -> skipped, no log row
        database, f1 = engine.fire("after_300", database, rules=[_rule(source_table="nope")],
                                   templates=_ROW_TPL, params={})
        eq([x.type for x in f1], ["rx_unknown_table"])
        ok(engine.LOG_TABLE not in database, "a rule that could not read its source never fired")
        # unknown target table -> fired, audited with created=0, finding
        database, f2 = engine.fire("after_300", database, rules=[_rule(target="nope")],
                                   templates=_ROW_TPL, params={})
        eq([x.type for x in f2], ["rx_unknown_table"])
        eq(list(database[engine.LOG_TABLE])[0]["created"], 0)
        # bad condition / text-template-for-add_rows / bad field expr
        _, f3 = engine.fire("after_300", _db(), rules=[_rule(condition="let(")],
                            templates=_ROW_TPL, params={})
        eq([x.type for x in f3], ["rx_bad_condition"])
        _, f4 = engine.fire("after_300", _db(), rules=[_rule()],
                            templates={"rows": "I am text"}, params={})
        eq([x.type for x in f4], ["rx_bad_template"])
        _, f5 = engine.fire("after_300", _db(), rules=[_rule()],
                            templates={"rows": [{"label": "{$missing_field}"}]}, params={})
        eq([x.type for x in f5], ["rx_bad_template"])
        ok(all(x.severity == "ERRR" for x in f1 + f2 + f3 + f4 + f5), "every failure is ERRR")
        recorded = [r["type"] for r in database["validation_issues"]]
        ok("rx_unknown_table" in recorded, "findings are recorded to validation_issues on a logged fire")
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
    _sandboxed(body)()


def test_sourceless_and_before_hook_semantics():
    def body(sandbox):
        with tempfile.TemporaryDirectory() as out_root:
            # a source-less file rule fires ONCE (e.g. a generated-file header), even with NO database
            rule = _rule(name="hdr", fire_when="before_300", source_table="", condition="",
                         action="file", target="gen/out.txt", template="txt")
            database, findings = engine.fire("before_300", None, rules=[rule],
                                             templates={"txt": "HEADER"}, params={}, files_root=out_root)
            ok(database is None and findings == [], "a before-hook file rule needs no database")
            with open(os.path.join(out_root, "gen", "out.txt"), encoding="utf-8") as handle:
                eq(handle.read(), "HEADER\n")
            # add_rows at a database-less hook -> a pointed finding, never a crash
            _, f = engine.fire("before_300", None,
                               rules=[_rule(fire_when="before_300")], templates=_ROW_TPL, params={})
            eq([x.type for x in f], ["rx_unknown_table"])
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
        ("fire_empty_hook_is_a_strict_noop", test_fire_empty_hook_is_a_strict_noop),
        ("add_rows_spawns_with_provenance", test_add_rows_spawns_with_provenance),
        ("multi_spec_row_template_and_log_replacement", test_multi_spec_row_template_and_log_replacement),
        ("failures_are_located_findings", test_failures_are_located_findings),
        ("file_action_appends_per_match", test_file_action_appends_per_match),
        ("engine_builds_the_full_e1_scope", test_engine_builds_the_full_e1_scope),
        ("sourceless_and_before_hook_semantics", test_sourceless_and_before_hook_semantics),
        ("rules_fire_in_csv_order_and_only_their_hook", test_rules_fire_in_csv_order_and_only_their_hook),
        ("builtin_config_ships_empty_rules", test_builtin_config_ships_empty_rules),
    ]))
