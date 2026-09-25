"""The Siemens phase handlers (safety/main.py), run HEADLESS against the real fixture documents -
the phase buttons without Tk.

This is the step-5 payoff of the PhaseContext seam: every handler reports only through
`ctx.emit/status/gate/render/records/halt`, so the whole Run-all chain executes here with the
App's REAL gate semantics (treatments applied, halt on effective severity) - exactly the dispatch
the App performs, minus the window. It catches the bug class the byte-parity oracle CANNOT see:
the oracle drives the chain functions directly with hand-passed arguments, while THIS runs the
handlers' own wiring (the 900 handler shipped for a whole step calling `engine.build(database)`
without its system - a guaranteed click-time crash the oracle never noticed).

Sandboxed like the oracle (module-attr overrides for the Database/Output roots), the treatments
registry copied aside (run_validation reconciles it - the builtin file must not be rewritten by a
test), and - also like the oracle - the document-MUTATING legs stay off: the 200 fill / 245 risky
handlers are not in the run_plan, and the sandbox forces `insert_interface_sheets` OFF (the builtin
fixture config ships it ON for real operator runs; a test must not edit the repo's fixture doc).
The source document's mtime is asserted unchanged after the whole chain.
"""
import os
import shutil
import tempfile

from _harness import run, eq, ok
from pipeline5 import config
from pipeline5.config import paths as p5paths
from pipeline5.findings import treatments
from pipeline5.systems.plc_based.siemens_s7.safety import main
from pipeline5.systems.plc_based.siemens_s7.safety.system import SYSTEM
from pipeline5.systems.system_contract import PhaseContext


class _Host:
    """The App's seam wiring, as collectors: what `App._ctx()` hands a handler, minus Tk/queue.
    gate/render mirror App._gate/_render - the treatments registry is APPLIED and the halt flag
    follows the EFFECTIVE severity (the severity contract), not the raw one."""

    def __init__(self):
        self.lines = []            # every (level, message) a handler emitted
        self.rendered = []         # every findings/records batch handed to gate/render/records
        self.halted = False

    def ctx(self):
        return PhaseContext(
            system=SYSTEM,
            emit=lambda level, msg: self.lines.append((level, msg)),
            status=lambda _text: None,
            gate=self._gate,
            render=self._render,
            records=lambda recs: self.rendered.append(list(recs)),
            halt=self._halt,
            lang="en",
        )

    def _apply(self, findings):
        self.rendered.append(list(findings))
        return treatments.apply(findings, treatments.load())

    def _gate(self, findings, label=""):
        if treatments.should_halt(self._apply(findings)):
            self.halted = True
            return False
        return True

    def _render(self, findings, label=""):
        if treatments.should_halt(self._apply(findings)):
            self.halted = True

    def _halt(self):
        self.halted = True

    def levels(self):
        return [level for level, _ in self.lines]


def _sandboxed(fn):
    """The oracle's isolation, harness-side: Database/Output into temp dirs (module-attr overrides),
    the treatments registry copied into the sandbox (run_validation's reconcile must not rewrite the
    builtin file), and `insert_interface_sheets` forced OFF (the one doc-writing leg inside a
    run_plan handler - the oracle skips it too; the repo's fixture doc stays untouched)."""
    def wrapped():
        orig_db, orig_out = p5paths._BUILTIN_DATABASE, p5paths._BUILTIN_OUTPUT
        orig_registry = treatments.registry_path
        orig_load_params = config.load_params
        with tempfile.TemporaryDirectory() as db_dir, tempfile.TemporaryDirectory() as out_dir:
            registry_copy = os.path.join(db_dir, "finding_treatments.csv")
            if os.path.isfile(orig_registry()):
                shutil.copy2(orig_registry(), registry_copy)

            def load_params_no_insert(path=None):
                params = orig_load_params(path)
                section = params.get("iolist_params")
                if isinstance(section, dict):
                    section["insert_interface_sheets"] = False
                return params

            p5paths._BUILTIN_DATABASE, p5paths._BUILTIN_OUTPUT = db_dir, out_dir
            treatments.registry_path = lambda: registry_copy
            config.load_params = load_params_no_insert
            try:
                fn()
            finally:
                p5paths._BUILTIN_DATABASE, p5paths._BUILTIN_OUTPUT = orig_db, orig_out
                treatments.registry_path = orig_registry
                config.load_params = orig_load_params
    return wrapped


def test_run_plan_executes_end_to_end():
    """Every run_plan phase through HANDLERS[phase.handler](ctx), each with a fresh host (handlers
    are self-contained) - exactly the dispatch the App performs. Each handler must complete (a
    crash = red), report a RSLT line (the success marker - a silent no-op handler is a bug), and
    NEVER halt on the clean fixture.

    RE-PINNED 2026-07-17 (the fire-alarm ruling): the two historic `iotag_duplicate` FAILs were a
    CONFIG defect - the F1/2+F2/2 rows shared one tag rule over one shared device - not a fixture
    defect; the rule now disambiguates with {$script_type}, so phase 500's 510 leg WRITES PLCTags
    (asserted below). A halt anywhere in the chain is a regression."""
    doc_path = config.load_params()["iolist_path"]
    doc_mtime = os.path.getmtime(doc_path)
    for number in SYSTEM.phases.run_order():
        phase = SYSTEM.phases.by_number(number)
        host = _Host()
        SYSTEM.handlers[phase.handler](host.ctx())
        ok("RSLT" in host.levels(), f"phase {number} ({phase.handler}) emitted a RSLT line "
                                    f"(got {host.levels()})")
        eq(host.halted, False, f"phase {number} must not halt on the clean fixture")
        if number == 500:
            ok(any("510:" in msg for lvl, msg in host.lines if lvl == "RSLT"),
               "the 510 leg reports its written tag surface (PLCTags is a real output again)")
    eq(os.path.getmtime(doc_path), doc_mtime,
       "the source I/O List was NOT modified by the run_plan chain")


def test_staging_fires_reaction_hooks():
    """The C-024 run-plan wiring: run_staging fires `before_300` (no database yet) then `after_300`
    (the freshly staged database) through the REAL rule loaders - deleting or typo'ing a hook call
    in safety/main.py dies HERE (the parity oracle drives staging directly and cannot see it).
    With the shipped EMPTY rules the fire is a no-op, so the staged output stays untouched."""
    from pipeline5.phases.chain_reactions import engine as reactions
    calls = []
    real_fire = reactions.fire

    seen = {}

    def recording_fire(hook, database, **kw):
        calls.append((hook, database is not None and "signals" in database))
        seen[hook] = None if database is None else {name: database[name].columns for name in database.names()}
        return real_fire(hook, database, **kw)

    host = _Host()
    reactions.fire = recording_fire
    try:
        SYSTEM.handlers["staging"](host.ctx())
    finally:
        reactions.fire = real_fire
    eq(calls, [("before_300", False), ("after_300", True)],
       "before fires with no database, after with the staged one - in that order")
    # P-012: the DECLARED hooks (System.reaction_hooks - what the template builder previews against)
    # are the fired ones, in order, each loading exactly the tables (+ declared columns) it saw
    eq(list(SYSTEM.reaction_hooks), [hook for hook, _db in calls], "the declared hooks = the fired ones")
    for hook, loader in SYSTEM.reaction_hooks.items():
        loaded = None if loader is None else loader(SYSTEM)
        eq(None if loaded is None else {name: loaded[name].columns for name in loaded.names()}, seen[hook],
           f"{hook}: the declared Database = the one the fire saw")
    ok("RSLT" in host.levels(), "staging completed with the hooks live")
    eq(host.halted, False, "the dark engine never perturbs the run")


def _reaction_project(project, params):
    """A PROJECT (tier 1 of the 4-tier walk) carrying its own chain-reaction rule pair: a before_300
    header, a before_300 add_rows that can only fail (no database yet), an after_300 line drilling
    the real params, an after_300 rule on a typo'd table, a rule on a hook the run-plan never fires,
    an after_300 rule whose condition does not compile (a decimal slice - it used to crash every
    hook), and an after_300 loop over the STAGED signals reading a declared column staging leaves
    unfilled (the loop-schema check used to reject it)."""
    import csv
    from ruamel.yaml import YAML
    shared = os.path.join(project, "config_project", "shared")
    rx_dir = os.path.join(project, "config_project", "systems", SYSTEM.id, "chain_reactions")
    os.makedirs(shared)
    os.makedirs(rx_dir)
    with open(os.path.join(shared, "project_params.yaml"), "w", encoding="utf-8") as handle:
        YAML(typ="safe").dump(params, handle)
    rules = [
        ["name", "fire_when", "source_table", "condition", "action", "target", "template", "comment"],
        ["probe_hdr", "before_300", "", "", "file", "rx/probe.txt", "hdr_txt", "a header before staging"],
        ["probe_early", "before_300", "", "", "add_rows", "signals", "rows_tpl", "no database exists yet"],
        ["probe_file", "after_300", "", "", "file", "rx/probe.txt", "probe_txt", "one line per run"],
        ["probe_bad", "after_300", "no_such_table", "", "file", "rx/bad.txt", "probe_txt", "a typo'd table"],
        ["probe_cold", "after_520", "", "", "file", "rx/cold.txt", "probe_txt", "a hook nobody fires"],
        ["probe_mal", "after_300", "signals", 'extract($mnemonic, /(\\d+)/, 1.3) = "1"', "file", "rx/mal.txt",
         "probe_txt", "1.3 typed for the slice 1:3"],
        ["probe_cols", "after_300", "", "", "file", "rx/cols.txt", "cols_txt", "a declared, unfilled column"],
        ["probe_top", "after_300", "signals", "", "file", "rx/top.txt", "top_txt", "the same, as a MATCHED row"],
        ["probe_count", "after_300", "", "", "file", "rx/count.txt", "count_txt", "a predicate in a strict hole"],
    ]
    with open(os.path.join(rx_dir, "reactions.csv"), "w", encoding="utf-8", newline="") as handle:
        csv.writer(handle).writerows(rules)
    with open(os.path.join(rx_dir, "templates.yaml"), "w", encoding="utf-8") as handle:
        handle.write("hdr_txt: |-\n  HEADER {$_rule.hook}\n"
                     "probe_txt: |-\n  [{$_params.project_code}] {$_rule.hook} {$_rule.name}\n"
                     "cols_txt: |-\n  @for $r in signals: [{$r.name_in_db}]\n"
                     "top_txt: |-\n  [{$name_in_db}]\n"
                     "count_txt: |-\n  PEC {count(signals, $script_type = \"PEC\")}\n"
                     "rows_tpl:\n  - label: \"x\"\n")


def _read_csv(path):
    import csv
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _rx_rendered(host):
    return {(f.type, f.location) for batch in host.rendered for f in batch
            if getattr(f, "type", "").startswith("rx_")}


def test_configured_rules_fire_through_the_real_run_plan():
    """E1 + E3 (refuter round 6): a PROJECT carrying its own rule pair (tier 1 of the 4-tier walk)
    through the REAL run_staging - the real loaders, the real params / templates / output-root
    defaults, the before_300 Deferred settled into the staged record, the run-plan's declared hooks,
    and every failure RENDERED. The unit tests inject all of these by hand; the empty shipped CSV
    makes the other smoke a no-op - so dropping a loader, a default, the settle, the hooks, or a
    ctx.render call dies only HERE."""
    params = config.load_params()                   # the builtin fixture params (doc paths absolute)
    previous_project = config.active_project()
    with tempfile.TemporaryDirectory() as project:
        _reaction_project(project, params)
        host = _Host()
        config.use_project(project)
        try:
            SYSTEM.handlers["staging"](host.ctx())
            out_root, db_dir = config.output_root(), config.database_dir()
            ok("RSLT" in host.levels(), "staging completed with configured rules live")
            eq(host.halted, False, "ERRR reactions never halt the run")
            with open(os.path.join(out_root, "rx", "probe.txt"), encoding="utf-8") as handle:
                eq(handle.read(), f"HEADER before_300\n[{params['project_code']}] after_300 probe_file\n",
                   "the real loaders fired both hooks: the before_300 header, then the after_300 line "
                   "drilling the REAL project params - written under the REAL output root")
            ok(not os.path.exists(os.path.join(out_root, "rx", "bad.txt")), "the failing rule wrote nothing")
            ok(not os.path.exists(os.path.join(out_root, "rx", "cold.txt")), "the unfired-hook rule never ran")
            ok(not os.path.exists(os.path.join(out_root, "rx", "mal.txt")), "the uncompilable rule never ran")
            staged = _read_csv(os.path.join(db_dir, "signals.csv"))
            with open(os.path.join(out_root, "rx", "cols.txt"), encoding="utf-8") as handle:
                cols = handle.read().splitlines()
            ok(len(staged) > 0 and len(cols) == len(staged) and all(c[:1] == "[" and c[-1:] == "]" for c in cols),
               f"one line per STAGED signal reading the declared-but-unfilled column ({len(cols)} vs {len(staged)})")
            with open(os.path.join(out_root, "rx", "top.txt"), encoding="utf-8") as handle:
                top = handle.read().splitlines()
            eq(len(top), len(staged), "…and as a MATCHED row's top-level field: one line per staged signal")
            pec = sum(1 for row in staged if row.get("script_type") == "PEC")
            with open(os.path.join(out_root, "rx", "count.txt"), encoding="utf-8") as handle:
                eq(handle.read(), f"PEC {float(pec)}\n", "a data-function predicate in a strict hole counts the staged rows")
            log = sorted((r["hook"], r["rule"], r["outcome"])
                         for r in _read_csv(os.path.join(db_dir, "chain_reactions_log.csv")))
            eq(log, [("after_300", "probe_bad", "rx_unknown_table"), ("after_300", "probe_cols", "ok"),
                     ("after_300", "probe_count", "ok"), ("after_300", "probe_file", "ok"),
                     ("after_300", "probe_top", "ok"),
                     ("before_300", "probe_early", "rx_unknown_table"), ("before_300", "probe_hdr", "ok")],
               "every firing audited - the database-less before_300 ones SETTLED into the staged record")
            recorded = [(r["type"], r["location"])
                        for r in _read_csv(os.path.join(db_dir, "validation_issues.csv"))
                        if r["type"].startswith("rx_")]
            eq(sorted(recorded), [("rx_bad_condition", "probe_mal"), ("rx_unfired_hook", "probe_cold"),
                                  ("rx_unknown_table", "probe_bad"), ("rx_unknown_table", "probe_early")],
               "every reaction finding recorded ONCE (the index-wide ones surfaced at both hooks)")
        finally:
            config.use_project(previous_project)
    eq(_rx_rendered(host), {("rx_unknown_table", "probe_early"), ("rx_unknown_table", "probe_bad"),
                            ("rx_unfired_hook", "probe_cold"), ("rx_bad_condition", "probe_mal")},
       "each finding was RENDERED through ctx.render - never silent")
    eq(sum(1 for batch in host.rendered for f in batch if getattr(f, "type", "") == "rx_unfired_hook"), 2,
       "the unfired-hook finding rendered at BOTH fires - each passes the run-plan's hooks (refuter round 11)")


def test_halted_staging_lists_the_deferred_trail_and_records_nothing():
    """Round-6 implications: when staging HALTS (a blocking FAIL - the dup type/index case saves its
    database, the no-I/O-sheet case writes NOTHING), the before_300 Deferred must not be settled
    into a half-committed record - and must not vanish either: its findings were rendered, and its
    firings are listed in the log (INFO, never hidden). after_300 never fires."""
    from pipeline5.findings.finding import Finding
    from pipeline5.phases.staging import iolist
    params = config.load_params()
    previous_project = config.active_project()
    real_stage = iolist.stage

    def halting_stage(*args, **kwargs):
        database, findings = real_stage(*args, **kwargs)
        return database, findings + [Finding(phase=300, type="probe_forced_fail", severity="FAIL",
                                             detail="forced halt", location="probe")]
    with tempfile.TemporaryDirectory() as project:
        _reaction_project(project, params)
        host = _Host()
        config.use_project(project)
        iolist.stage = halting_stage
        try:
            SYSTEM.handlers["staging"](host.ctx())
            out_root, db_dir = config.output_root(), config.database_dir()
            eq(host.halted, True, "the forced FAIL halted staging")
            with open(os.path.join(out_root, "rx", "probe.txt"), encoding="utf-8") as handle:
                eq(handle.read(), "HEADER before_300\n",
                   "before_300 ran (its append-only side effect stays); after_300 never fired")
            eq(_read_csv(os.path.join(db_dir, "chain_reactions_log.csv")), [],
               "no reaction audit was committed into the halted run's record")
            ok(not any(r["type"].startswith("rx_")
                       for r in _read_csv(os.path.join(db_dir, "validation_issues.csv"))),
               "...and no reaction finding either")
        finally:
            iolist.stage = real_stage
            config.use_project(previous_project)
    listed = [msg for level, msg in host.lines if level == "INFO" and "not recorded, staging halted" in msg]
    eq(len(listed), 2, "both deferred before_300 firings are LISTED in the log")
    ok(any("probe_hdr: ok (1 created)" in msg for msg in listed), "...the header's success")
    ok(any("probe_early: rx_unknown_table" in msg for msg in listed), "...and the failure's outcome")
    eq(_rx_rendered(host), {("rx_unknown_table", "probe_early"), ("rx_unfired_hook", "probe_cold"),
                            ("rx_bad_condition", "probe_mal")},
       "before_300 - the ONLY fire of a halted run - rendered its own finding, the unfired hook (it "
       "passes the run-plan's hooks), and after_300's malformed rule (another hook's rule still "
       "surfaces): refuter round 7 E1/E2")


def test_a_corrupt_reaction_record_is_reported_not_crashed_or_overwritten():
    """Refuter round 8 R4 through the real run-plan: a hand-edited chain_reactions_log.csv gone ragged
    used to crash run_staging (after staging had saved and before_300 had appended) - no RSLT, the
    trail lost. It is a RENDERED finding now, the run completes, and the ragged file is untouched."""
    params = config.load_params()
    previous_project = config.active_project()
    with tempfile.TemporaryDirectory() as project:
        _reaction_project(project, params)
        host = _Host()
        config.use_project(project)
        try:
            db_dir = config.database_dir()
            os.makedirs(db_dir, exist_ok=True)
            ragged = os.path.join(db_dir, "chain_reactions_log.csv")
            with open(ragged, "w", encoding="utf-8", newline="") as handle:
                handle.write("uid,hook,rule,action,target,matches,created,outcome\n"
                             "u1,after_500,x,file,t,1,1,ok,EXTRA-CELL\n")
            with open(ragged, "rb") as handle:
                before = handle.read()
            SYSTEM.handlers["staging"](host.ctx())
            ok("RSLT" in host.levels(), "staging completed - the corrupt record did not crash it")
            eq(host.halted, False, "an ERRR never halts")
            with open(ragged, "rb") as handle:
                eq(handle.read(), before, "the ragged record was left untouched")
        finally:
            config.use_project(previous_project)
    eq(sum(1 for batch in host.rendered for f in batch if getattr(f, "type", "") == "rx_record_unreadable"), 2,
       "RENDERED twice - by the before_300 settle AND the after_300 fire: neither path is silent")


def _spawn_project(project, params, header: bool = False):
    """A project whose after_300 rules CASCADE within one hook: the templates.yaml manual's own
    example (spawn a DIAG signal per `A` row), then a rule that counts and lists those spawns.
    `header` adds a before_300 file rule - the run-plan then SETTLES it into the staged database."""
    import csv
    from ruamel.yaml import YAML
    shared = os.path.join(project, "config_project", "shared")
    rx_dir = os.path.join(project, "config_project", "systems", SYSTEM.id, "chain_reactions")
    os.makedirs(shared)
    os.makedirs(rx_dir)
    with open(os.path.join(shared, "project_params.yaml"), "w", encoding="utf-8") as handle:
        YAML(typ="safe").dump(params, handle)
    with open(os.path.join(rx_dir, "reactions.csv"), "w", encoding="utf-8", newline="") as handle:
        csv.writer(handle).writerows([
            ["name", "fire_when", "source_table", "condition", "action", "target", "template", "comment"],
            ["probe_spawn", "after_300", "signals", '$script_type = "A"', "add_rows", "signals", "diag_rows", ""],
            ["probe_read", "after_300", "", "", "file", "rx/diag.txt", "diag_txt", "reads the spawns"],
        ] + ([["probe_hdr", "before_300", "", "", "file", "rx/hdr.txt", "hdr_txt", "settled"]] if header else []))
    with open(os.path.join(rx_dir, "templates.yaml"), "w", encoding="utf-8") as handle:
        handle.write("diag_rows:\n  - script_type: \"DIAG\"\n    mnemonic: \"DIAG-{$mnemonic}\"\n"
                     "diag_txt: |-\n  DIAG rows: {count(signals, $script_type = \"DIAG\")}\n"
                     "  @for $s in signals where $script_type = \"DIAG\": {$s.spawned_by}\n"
                     "hdr_txt: |-\n  HEADER {$_rule.hook}\n")


def _staged_count(host):
    """The RSLT line's `staged N signals` N (what the run REPORTS it saved)."""
    import re
    for level, msg in host.lines:
        match = re.search(r"staged (\d+) signals", msg) if level == "RSLT" else None
        if match:
            return int(match.group(1))
    return None


def test_a_cascade_within_one_hook_through_the_real_run_plan():
    """Refuter round 9 (medium) through run_staging: the manual's own example spawned 24 DIAG signals,
    yet the next rule in the same hook counted 0.0 and listed none - every rule audited `ok`, nothing
    rendered: a SILENT wrong answer in the engine's core use (a chain reaction within one hook)."""
    params = config.load_params()
    previous_project = config.active_project()
    with tempfile.TemporaryDirectory() as project:
        _spawn_project(project, params)
        host = _Host()
        config.use_project(project)
        try:
            SYSTEM.handlers["staging"](host.ctx())
            saved = _read_csv(os.path.join(config.database_dir(), "signals.csv"))
            sources = sum(1 for row in saved if row.get("script_type") == "A")
            spawned = sum(1 for row in saved if row.get("script_type") == "DIAG")
            ok(sources > 0 and spawned == sources, f"one DIAG spawn per A row, saved ({spawned} vs {sources})")
            with open(os.path.join(config.output_root(), "rx", "diag.txt"), encoding="utf-8") as handle:
                eq(handle.read(), f"DIAG rows: {float(sources)}\n" + "probe_spawn\n" * sources,
                   "the later rule COUNTED and LISTED the earlier rule's spawns")
            eq(_staged_count(host), len(saved), "the RSLT count matches the saved signals")
        finally:
            config.use_project(previous_project)


def test_the_builder_models_what_the_after_300_fire_gets():
    """C-025 refute round 1 + the implications check: the template builder's after_300 Database was the
    Database/ folder - the last SAVED state: a previous run's spawns (with their spawned_by /
    source_uid columns), later phases' write-backs, no settled record. The builder's Session now
    models the run-plan - System.reaction_hooks' in-memory staging + a settled before_300 with
    business - and here it is compared with what the REAL after_300 fire gets, on a SECOND run
    (after the first saved its spawns)."""
    from pipeline5.phases.chain_reactions import engine as reactions
    from pipeline5.workbench import template_doc
    params = config.load_params()
    previous_project = config.active_project()
    seen, real_fire = {}, reactions.fire

    def shape(database):
        return {name: (database[name].effective_columns(), len(database[name])) for name in database.names()}

    def recording_fire(hook, database, **kw):
        if hook == "after_300":                       # the fire's input, before it runs - and the model
            seen["fired"] = shape(database)
            seen["model"] = shape(template_doc.Session(None).base("after_300"))
        return real_fire(hook, database, **kw)

    with tempfile.TemporaryDirectory() as project:
        _spawn_project(project, params, header=True)
        config.use_project(project)
        try:
            SYSTEM.handlers["staging"](_Host().ctx())             # run 1: its spawns saved into signals.csv
            ok("spawned_by" in _read_csv(os.path.join(config.database_dir(), "signals.csv"))[0],
               "the saved Database carries run 1's spawns - what the old builder previewed against")
            reactions.fire = recording_fire
            SYSTEM.handlers["staging"](_Host().ctx())             # run 2: re-staged from the documents
        finally:
            reactions.fire = real_fire
            config.use_project(previous_project)
    fired, model = seen["fired"], seen["model"]
    eq(sorted(model), sorted(fired), "the same tables - the settled record included")
    for name in fired:
        eq(model[name][0], fired[name][0], f"{name}: the same columns (no leaked spawn columns)")
    for name in ("signals", "diagnosis_cabinets", "chain_reactions_log"):
        eq(model[name][1], fired[name][1], f"{name}: the same rows (the saved spawns are not in the fire's input)")
    ok("spawned_by" not in fired["signals"][0], "run 2's fire gets no spawn column")


def test_spawns_are_saved_beside_a_ragged_record():
    """Refuter round 9: with a ragged chain_reactions_log.csv the engine skipped the WHOLE save - the
    after_300 spawns silently never reached signals.csv while RSLT reported them. The rest of the
    Database is saved now; only the unreadable record is left untouched (and reported)."""
    params = config.load_params()
    previous_project = config.active_project()
    with tempfile.TemporaryDirectory() as project:
        _spawn_project(project, params)
        host = _Host()
        config.use_project(project)
        try:
            db_dir = config.database_dir()
            os.makedirs(db_dir, exist_ok=True)
            ragged = os.path.join(db_dir, "chain_reactions_log.csv")
            with open(ragged, "w", encoding="utf-8", newline="") as handle:
                handle.write("uid,hook,rule,action,target,matches,created,outcome\nu1,after_500,x,f,t,1,1,ok,EXTRA\n")
            with open(ragged, "rb") as handle:
                before = handle.read()
            SYSTEM.handlers["staging"](host.ctx())
            saved = _read_csv(os.path.join(db_dir, "signals.csv"))
            ok(any(row.get("script_type") == "DIAG" for row in saved), "the spawns were SAVED")
            eq(_staged_count(host), len(saved), "the RSLT count matches the saved signals")
            with open(ragged, "rb") as handle:
                eq(handle.read(), before, "the ragged record is untouched")
        finally:
            config.use_project(previous_project)
    ok(any(getattr(f, "type", "") == "rx_record_unreadable" for batch in host.rendered for f in batch),
       "the unreadable record was rendered")


def _rules_project(project, params, rules, templates_text):
    """A minimal project carrying exactly `rules` (reactions.csv rows, header first) + `templates_text`."""
    import csv
    from ruamel.yaml import YAML
    shared = os.path.join(project, "config_project", "shared")
    rx_dir = os.path.join(project, "config_project", "systems", SYSTEM.id, "chain_reactions")
    os.makedirs(shared)
    os.makedirs(rx_dir)
    with open(os.path.join(shared, "project_params.yaml"), "w", encoding="utf-8") as handle:
        YAML(typ="safe").dump(params, handle)
    with open(os.path.join(rx_dir, "reactions.csv"), "w", encoding="utf-8", newline="") as handle:
        csv.writer(handle).writerows(rules)
    with open(os.path.join(rx_dir, "templates.yaml"), "w", encoding="utf-8") as handle:
        handle.write(templates_text)


def test_a_blank_range_end_invents_nothing_on_the_real_fixture():
    """Refuter round 10 + the user's decision (2026-09-25: a BLANK range end is an EMPTY range):
    a byte map over the staged node rows used to invent a `QB0` line for every input-only node (its Q
    start/end are blank - they read as 0), audited ok. The file must hold exactly the REAL Q bytes."""
    params = config.load_params()
    previous_project = config.active_project()
    with tempfile.TemporaryDirectory() as project:
        _rules_project(project, params, [
            ["name", "fire_when", "source_table", "condition", "action", "target", "template", "comment"],
            ["byte_map", "after_300", "signals", "present($I_startByte) or present($Q_startByte)", "file",
             "rx/bytes.txt", "bytes_txt", "the refuter's byte map"],
        ], "bytes_txt: |-\n  @for $b in {$Q_startByte}..{$Q_endByte}: QB{$b}\n")
        host = _Host()
        config.use_project(project)
        try:
            SYSTEM.handlers["staging"](host.ctx())
            staged = _read_csv(os.path.join(config.database_dir(), "signals.csv"))
            with open(os.path.join(config.output_root(), "rx", "bytes.txt"), encoding="utf-8") as handle:
                got = handle.read()
        finally:
            config.use_project(previous_project)
    expected, blank_q = "", 0
    for row in staged:
        start, stop = (row.get("Q_startByte") or "").strip(), (row.get("Q_endByte") or "").strip()
        if not ((row.get("I_startByte") or "").strip() or start):
            continue                                                   # not matched by the condition
        if start and stop:
            expected += "\n".join(f"QB{b}" for b in range(int(float(start)), int(float(stop)) + 1)) + "\n"
        else:
            expected += "\n"                                           # blank Q: an EMPTY range
            blank_q += 1
    ok(blank_q > 0, f"the fixture has input-only nodes with blank Q bytes ({blank_q})")
    eq(got, expected, "exactly the real Q bytes - no invented QB0 for a blank end")


def test_310_leg_appends_reaction_findings_to_the_existing_record():
    """Refuter round 7 B3 through the real run-plan: the 310 leg (Stage I/O List) stages a Database
    WITHOUT validation_issues; a reaction finding used to create an empty table and save it OVER the
    record an earlier phase wrote. It is appended to the on-disk record now."""
    from pipeline5.findings.finding import Finding, record_standalone
    params = config.load_params()
    previous_project = config.active_project()
    with tempfile.TemporaryDirectory() as project:
        _reaction_project(project, params)
        host = _Host()
        config.use_project(project)
        try:
            db_dir = config.database_dir()
            record_standalone([Finding(phase=110, type="probe_prior", severity="FAIL",
                                       detail="from phase 110", location="X1")], directory=db_dir)
            SYSTEM.handlers["staging"](host.ctx(), only=310)
            recorded = {(r["type"], r["location"]) for r in _read_csv(os.path.join(db_dir, "validation_issues.csv"))}
            ok(("probe_prior", "X1") in recorded, "the earlier phase's record SURVIVED the 310 leg")
            ok({("rx_unknown_table", "probe_bad"), ("rx_unknown_table", "probe_early")} <= recorded,
               "...with the reaction findings appended")
        finally:
            config.use_project(previous_project)


def test_sub_phase_dispatch():
    """A dropdown action: the parent handler with only=<sub> - the 310 stage-I/O-List leg, plus a
    validation sub (110), through the same dispatch the App's _sub_worker performs."""
    host = _Host()
    phase = SYSTEM.phases.phase_of_sub(310)
    SYSTEM.handlers[phase.handler](host.ctx(), only=310)
    ok(any("310" in msg for _lvl, msg in host.lines), "the 310 leg announces itself")
    ok("RSLT" in host.levels(), "the 310 leg reports a RSLT")
    host2 = _Host()
    phase = SYSTEM.phases.phase_of_sub(110)
    SYSTEM.handlers[phase.handler](host2.ctx(), only=110)
    ok("RSLT" in host2.levels(), "the 110 validator reports a RSLT")


if __name__ == "__main__":
    import sys
    sys.exit(run("siemens_main_handlers", [
        ("run_plan_executes_end_to_end", _sandboxed(test_run_plan_executes_end_to_end)),
        ("staging_fires_reaction_hooks", _sandboxed(test_staging_fires_reaction_hooks)),
        ("configured_rules_fire_through_the_real_run_plan",
         _sandboxed(test_configured_rules_fire_through_the_real_run_plan)),
        ("halted_staging_lists_the_deferred_trail_and_records_nothing",
         _sandboxed(test_halted_staging_lists_the_deferred_trail_and_records_nothing)),
        ("a_corrupt_reaction_record_is_reported_not_crashed_or_overwritten",
         _sandboxed(test_a_corrupt_reaction_record_is_reported_not_crashed_or_overwritten)),
        ("a_cascade_within_one_hook_through_the_real_run_plan",
         _sandboxed(test_a_cascade_within_one_hook_through_the_real_run_plan)),
        ("the_builder_models_what_the_after_300_fire_gets", _sandboxed(test_the_builder_models_what_the_after_300_fire_gets)),
        ("spawns_are_saved_beside_a_ragged_record", _sandboxed(test_spawns_are_saved_beside_a_ragged_record)),
        ("a_blank_range_end_invents_nothing_on_the_real_fixture",
         _sandboxed(test_a_blank_range_end_invents_nothing_on_the_real_fixture)),
        ("310_leg_appends_reaction_findings_to_the_existing_record",
         _sandboxed(test_310_leg_appends_reaction_findings_to_the_existing_record)),
        ("sub_phase_dispatch", _sandboxed(test_sub_phase_dispatch)),
    ]))
