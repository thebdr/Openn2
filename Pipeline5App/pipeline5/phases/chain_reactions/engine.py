"""The chain-reaction RULE ENGINE - compile the config rules, match, spawn/append, audit, `fire`.

WHERE YOU MEET IT: a system's run-plan fires hooks around its phase work (Siemens:
src://pipeline5/systems/plc_based/siemens_s7/safety/main.py fires `before_300`/`after_300` around
the staging leg), so a phase button and Run-all trigger reactions identically. With no rules
configured for a hook, `fire` is a strict NO-OP - it touches neither the Database nor the disk
(the byte-parity guarantee: an empty rule set changes nothing).

THE RULE (one row of `chain_reactions/reactions.csv` - per-system config, 4-tier resolved):

    name          the rule's id (REQUIRED) - lands in the log + in every spawned row's `spawned_by`
    fire_when     `before_<phase>` / `after_<phase>` (e.g. after_300) - which hook fires it; a hook
                  the system's run-plan never fires is reported (the run-plan passes its `hooks`)
    source_table  the SSOT table whose rows are tested; EMPTY = fire ONCE with an empty row scope
                  (a source-less file rule, e.g. a generated-file header)
    condition     an expr predicate run per source row (empty = every row matches); it must
                  COMPILE when the rules are compiled (a typo is caught even over an empty table)
    action        `add_rows` - spawn rows into an SSOT table | `file` - render + APPEND to a file
    target        add_rows: the target TABLE name | file: the file path (an expr template,
                  rendered per match; relative paths land under the project output root)
    template      the templates.yaml entry: add_rows needs a ROW template (a non-empty list of
                  {field: expr-template} maps - one spawned row per entry per match);
                  file needs a TEXT template (src://pipeline5/language/tempemplator.py)
    comment       free text for the reader

THE SCOPE an expression sees (the E1 layering): the matched source row's fields at top level,
`_params` = the project params (dotted: {$_params.project_code}), `_rule` = {name, hook},
`_db` = every SSOT table (expr's data functions + the @for table queries read it), each row carrying
EVERY column of its table (an absent cell as "") - a freshly staged row lacks the columns later
phases fill, yet the renderer's loop-column check must see the table's real schema.

APPEND is the file action's ONLY mode (user decision 2026-07-16): the file is created if absent and
APPENDED otherwise - the USER is responsible for lifecycle handling (e.g. a `before_<phase>` rule
that opens a fresh header, or deleting the file between runs).

THE AUDIT TRAIL is the `chain_reactions_log` SSOT table: one row per rule FIRED at a hook (hook,
rule, action, target, match count, rows-or-lines created - counted as they are made, so a mid-action
failure keeps the true partial count - and `outcome` = "ok" or the failure's finding type), REPLACED
per hook on each firing so the Explorer shows the LAST run - a failed re-fire replaces the previous
run's success row too. A Database that never loaded the audit or the findings record (the 310 leg
stages only signals + diagnosis_cabinets) APPENDS to the on-disk one - never overwrites it. A hook with NO database yet (before_300: nothing is
staged) cannot persist anything: its fire returns a `Deferred` (the audit rows + findings) that the
run-plan hands to `settle` once the phase has staged its database.

FAILURES ARE FINDINGS, NEVER SILENT AND NEVER A CRASH - each a located ERRR (the rule is skipped,
the run continues; ERRR = possibly-incomplete output, per the severity contract), rendered through
the handler's `ctx.render` and recorded (uid-deduplicated) to `validation_issues`:

    rx_bad_rule         a malformed reactions.csv row (no name / bad hook / action / target /
                        template) - dropped at compile; a row the compiler cannot even read is
                        named by its position (`<row n>`) - compiling NEVER raises, since the
                        whole index compiles at every hook's fire
    rx_bad_condition    the condition does not compile (dropped at compile) or fails to evaluate
    rx_bad_template     the template is missing, the wrong kind for the action, malformed, or fails
                        to render (a strict hole, a template error)
    rx_unknown_table    a source / target table absent at this hook
    rx_file_write       the rendered target path cannot be written (e.g. a Windows-invalid `"`)
    rx_rules_unreadable / rx_templates_unreadable / rx_params_unreadable
                        a config file does not load (e.g. a YAML syntax error) - the hook's rules
                        are all blocked, each audited with that outcome
    rx_unfired_hook     a rule on a hook the run-plan never fires (it would never run) - dropped
    rx_record_unreadable / rx_record_unwritable
                        the reaction record (audit / validation_issues) does not load - a hand-edited
                        CSV gone ragged: left UNTOUCHED, nothing recorded over it - or does not save
                        (a file held open, e.g. by Excel); rendered, never a crash
    rx_rule_crashed     the backstop - an unforeseen defect, reported with its exception type

A problem of the rule INDEX itself (a row naming no hook, an unfired hook, an unreadable
reactions.csv) belongs to no single hook: it is every hook's business - rendered at each fire,
recorded once (the file-level findings carry phase 0, so the uid is the same whichever hook - and
whichever PHASE - meets the file). A HALTED staging commits no reaction record (the run-plan lists the deferred
before_300 firings in the log instead - a half-committed record would mix runs).

KNOWN BOUNDARY (deliberate, until the generated-signals spec review): an `after_300` `add_rows`
spawn persists into the SAVED Database - visible in the Explorer - but downstream phases RE-STAGE
from the source document, so spawned `signals` rows do not yet flow into generation. The flagship
absorption (spawned signals consumed by every phase) lands with its own reviewed step.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from pipeline5 import config
from pipeline5.findings.finding import Finding, record, validation_issues_table
from pipeline5.language import expr
from pipeline5.language import tempemplator
from pipeline5.language.expr import ExprError
from pipeline5.language.tempemplator import TempemplatorError
from pipeline5.truth.database import Database
from pipeline5.truth.table import Table

_HOOK = re.compile(r"^(before|after)_(\d+)$")
_ACTIONS = ("add_rows", "file")

LOG_TABLE = "chain_reactions_log"
RULES_FILE = "chain_reactions/reactions.csv"
TEMPLATES_FILE = "chain_reactions/templates.yaml"


def chain_reactions_log_table() -> Table:
    """The audit-trail SSOT table: one row per rule fired at its hook (see the module chapter)."""
    return Table(LOG_TABLE,
                 columns=["uid", "hook", "rule", "action", "target", "matches", "created", "outcome"],
                 key_columns=["hook", "rule", "target"])


@dataclass(frozen=True)
class Rule:
    """One compiled reaction rule (the reactions.csv row, validated)."""
    name: str
    fire_when: str
    source_table: str
    condition: str
    action: str
    target: str
    template: str
    comment: str = ""

    @property
    def phase(self) -> int:
        """The hook's phase number (findings carry it)."""
        return int(_HOOK.match(self.fire_when).group(2))


@dataclass
class Deferred:
    """What a DATABASE-LESS hook (before_300 - no SSOT is staged yet) could not persist: its audit
    rows + findings. The run-plan passes it to `settle` once the phase has staged a database."""
    hook: str
    log_rows: list = field(default_factory=list)
    findings: list = field(default_factory=list)


def _f(phase: int, type_: str, detail: str, location: str) -> Finding:
    return Finding(phase=phase, type=type_, severity="ERRR", detail=detail, location=location)


def _hook_phase(hook: str) -> int:
    match = _HOOK.match(hook)
    return int(match.group(2)) if match else 0


def _compile(rows) -> tuple:
    """reactions.csv rows -> (rules, [(hook_or_None, finding)]): each finding tagged with the hook
    its row names (None when unparseable), so `fire` knows which hook OWNS it. The rule index is
    compiled at EVERY hook's fire, so compiling must never raise: a row the compiler cannot even
    read is an index problem (owner None), never a crash of every hook (refuter round 7)."""
    rules, tagged = [], []
    for number, row in enumerate(rows, start=1):
        try:
            rule, problem = _compile_row(row)
        except Exception as error:                    # the backstop - named by position, not content
            rule, problem = None, (None, _f(0, "rx_bad_rule", f"reactions.csv row {number} cannot be "
                                            f"compiled: {type(error).__name__}: {error}", f"<row {number}>"))
        if rule is not None:
            rules.append(rule)
        if problem is not None:
            tagged.append(problem)
    return rules, tagged


def _compile_row(row) -> tuple:
    """One reactions.csv row -> (Rule, None) or (None, (owner_hook_or_None, finding))."""
    name = (row.get("name") or "").strip()
    fire_when = (row.get("fire_when") or "").strip().lower()
    action = (row.get("action") or "").strip().lower()
    target = (row.get("target") or "").strip()
    template = (row.get("template") or "").strip()
    condition = (row.get("condition") or "").strip()
    hook = _HOOK.match(fire_when)
    owner = fire_when if hook else None
    phase = int(hook.group(2)) if hook else 0
    problems = []
    if not name:
        problems.append("name is empty (the rule's id - row: "
                        f"fire_when={fire_when!r}, action={action!r}, target={target!r})")
    if not hook:
        problems.append(f"fire_when {fire_when!r} is not before_<phase>/after_<phase>")
    if action not in _ACTIONS:
        problems.append(f"action {action!r} is not one of {_ACTIONS}")
    if not target:
        problems.append("target is empty (a table name or a file path)")
    if not template:
        problems.append("template is empty (a templates.yaml entry name)")
    if problems:
        return None, (owner, _f(phase, "rx_bad_rule", "; ".join(problems), name or "<unnamed rule>"))
    try:                                              # compile-only: a typo is caught even when
        issues = expr.check(condition)                # no row would ever reach the condition
        message = issues[0].message if issues else ""
    except Exception as error:                        # a checker defect is still THIS rule's finding
        message = f"{type(error).__name__}: {error}"
    if message:
        return None, (owner, _f(phase, "rx_bad_condition", f"condition {condition!r}: {message}", name))
    return Rule(name=name, fire_when=fire_when, source_table=(row.get("source_table") or "").strip(),
                condition=condition, action=action, target=target, template=template,
                comment=(row.get("comment") or "").strip()), None


def compile_rules(rows) -> tuple:
    """reactions.csv rows -> (rules, findings). A malformed row (incl. a condition that does not
    compile) becomes a located ERRR finding and is DROPPED (the engine never fires a rule it could
    not validate)."""
    rules, tagged = _compile(rows)
    return rules, [finding for _owner, finding in tagged]


def _template_problem(rule: Rule, templates: dict):
    """Why the rule's template cannot serve its action (None = fine) - checked BEFORE any matching,
    so a missing / wrong-kind / malformed template is reported even when nothing matches."""
    if rule.template not in templates:
        return f"template {rule.template!r} is not in templates.yaml"
    body = templates[rule.template]
    if rule.action == "file":
        if not isinstance(body, str):
            return (f"template {rule.template!r} is a ROW template (a list) - "
                    "the file action needs a TEXT template")
        return None
    if not isinstance(body, list) or not body:
        return f"template {rule.template!r} is not a ROW template (a non-empty list of field maps)"
    for number, spec in enumerate(body, start=1):
        if not isinstance(spec, dict) or not spec:
            return f"row template {rule.template!r} entry {number} is not a {{field: expr}} map"
        for name, value in spec.items():
            if value is None:
                return (f"row template {rule.template!r} entry {number}: field {name!r} has no "
                        "value (write '' for an empty field)")
    return None


def _scope(row: dict, rule: Rule, params: dict, db_tables: dict) -> dict:
    """The E1 layered expression scope for one matched row (see the module chapter)."""
    return {**row, "_params": params, "_rule": {"name": rule.name, "hook": rule.fire_when},
            "_db": db_tables}


def _matches(rule: Rule, database, params: dict, db_tables: dict) -> tuple:
    """The source rows the rule fires for: (rows, finding_or_None). No source_table -> ONE empty
    row (a fire-once rule). Bad table / a condition failing to evaluate -> the located finding."""
    if not rule.source_table:
        candidates = [{}]
    else:
        if database is None or rule.source_table not in database:
            return [], _f(rule.phase, "rx_unknown_table",
                          f"source table {rule.source_table!r} is not in the database at this hook",
                          rule.name)
        candidates = _complete_rows(database[rule.source_table])
    if not rule.condition:
        return candidates, None
    try:
        return [r for r in candidates
                if expr.test(rule.condition, _scope(r, rule, params, db_tables))], None
    except ExprError as error:
        return [], _f(rule.phase, "rx_bad_condition", str(error), rule.name)


def _spawn_rows(rule: Rule, matched: list, database, templates: dict,
                params: dict, db_tables: dict, tally: dict) -> list:
    """The add_rows action: per matched row, per row-spec of the ROW template, spawn one expr-filled
    row into the target table WITH provenance (spawned_by = the rule, source_uid = the trigger).
    Counts into `tally["created"]` AS IT GOES (a mid-action failure keeps the true partial count).
    Returns the findings."""
    if database is None or rule.target not in database:
        return [_f(rule.phase, "rx_unknown_table",
                   f"target table {rule.target!r} is not in the database at this hook", rule.name)]
    table = database[rule.target]
    for row in matched:
        scope = _scope(row, rule, params, db_tables)
        for row_spec in templates[rule.template]:
            try:
                values = {str(name): expr.render(str(tpl), scope, mode="strict")
                          for name, tpl in row_spec.items()}
            except ExprError as error:
                return [_f(rule.phase, "rx_bad_template", f"row template {rule.template!r}: {error}", rule.name)]
            values["spawned_by"] = rule.name
            values.setdefault("source_uid", str(row.get("uid") or ""))
            table.add(**values)
            tally["created"] += 1
    return []


def _append_file(rule: Rule, matched: list, templates: dict, params: dict,
                 db_tables: dict, files_root: str, tally: dict) -> list:
    """The file action: per matched row, render the TEXT template and APPEND it (+ newline) to the
    expr-rendered target path (relative -> under `files_root`). Counts the lines written into
    `tally["created"]` as it goes. Returns the findings."""
    for row in matched:
        scope = _scope(row, rule, params, db_tables)
        try:
            path = expr.render(rule.target, scope, mode="strict")
            text = tempemplator.render_template(rule.template, templates, scope)
        except (ExprError, TempemplatorError) as error:
            return [_f(rule.phase, "rx_bad_template", str(error), rule.name)]
        if not os.path.isabs(path):
            path = os.path.join(files_root, path)
        try:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            with open(path, "a", encoding="utf-8") as handle:      # APPEND is the only mode (user decision)
                handle.write(text + "\n")
        except OSError as error:                                   # e.g. a `"` a quoted tag rendered in
            return [_f(rule.phase, "rx_file_write", f"cannot write {path!r}: {error.strerror or error}",
                       rule.name)]
        tally["created"] += text.count("\n") + 1
    return []


def _load(loader, type_: str, what: str):
    """(value, None) or (None, the located finding) - a config file that does not load (a YAML
    syntax error, e.g. a plain value starting with `@`) is a finding, never a crash. FILE-level, so
    phase 0: the same broken file is ONE finding whichever hook meets it (refuter round 8)."""
    try:
        return loader(), None
    except Exception as error:
        return None, _f(0, type_, f"{what} does not load: {error}", what)


def _complete_rows(table) -> list:
    """The table's rows as fresh dicts, each carrying EVERY column of the table (declared + extras; an
    absent cell as "" - exactly how expr reads a missing key). A freshly STAGED row lacks the columns
    later phases fill, yet they are the table's columns all the same - so a matched row's top-level
    `{$name_in_db}` and a loop's `{$r.name_in_db}` both see them (refuter rounds 7 + 8)."""
    columns = table.effective_columns()
    return [{column: row.get(column, "") for column in columns} for row in table]


def _db_tables(database) -> dict:
    """The E1 `_db` layer: {table: complete rows} (see `_complete_rows`) - so the renderer's
    loop-column check sees each table's real schema."""
    return {name: _complete_rows(database[name]) for name in database.names()}


def _attach(database, factory, name: str):
    """The database's `name` table - or, when this Database never loaded one (the 310 leg stages only
    signals + diagnosis_cabinets), the ON-DISK record, so appending and saving never overwrite what
    earlier phases recorded (refuter round 7: a reaction finding wiped a phase-110 record)."""
    if name not in database:
        database.add_table(Database([factory()]).load(config.database_dir())[name])
    return database[name]


def _record_new(database, findings) -> int:
    """Record the findings not yet in `validation_issues` (by uid - a malformed rule surfaces at every
    hook's fire, but lands in the record ONCE). Returns the count recorded; the caller saves."""
    known = {r.get("uid") for r in _attach(database, validation_issues_table, "validation_issues")}
    fresh = []
    for finding in findings:
        if finding.uid not in known:
            known.add(finding.uid)
            fresh.append(finding)
    if fresh:
        record(database, fresh)
    return len(fresh)


def _persist(database, hook: str, log_rows: list, findings: list) -> list:
    """Replace `hook`'s audit rows with this firing's, record its findings, save the database. A record
    that will not LOAD (a hand-edited CSV gone ragged) is left untouched - nothing is recorded over it;
    one that will not SAVE (a file held open, e.g. by Excel) is reported. Either is a located finding,
    never a crash (refuter round 8). Returns those findings for the caller to surface."""
    phase, where = _hook_phase(hook), config.database_dir()
    try:
        log = _attach(database, chain_reactions_log_table, LOG_TABLE)
        _attach(database, validation_issues_table, "validation_issues")
    except Exception as error:
        return [_f(phase, "rx_record_unreadable",
                   f"the reaction record does not load - left untouched, nothing recorded: {error}", where)]
    log.rows = [r for r in log.rows if r.get("hook") != hook]   # this hook's audit reflects THE LAST run
    log.extend(log_rows)
    _record_new(database, findings)
    try:
        database.save(where)
    except OSError as error:
        return [_f(phase, "rx_record_unwritable",
                   f"the record could not be saved (a file held open by another program?): {error}", where)]
    return []


def settle(database, deferred) -> list:
    """Persist a database-less hook's `Deferred` (its audit rows + findings) into the database the
    phase has now staged. None (the hook had no rules) is a no-op. Returns the persistence findings
    (see `_persist`) for the run-plan to render."""
    if deferred is None or database is None:
        return []
    return _persist(database, deferred.hook, deferred.log_rows, deferred.findings)


def _finish(hook: str, database, log_rows: list, findings: list) -> tuple:
    """Persist this firing - or, with no database yet, hand it back as a `Deferred`."""
    if database is None:
        return Deferred(hook=hook, log_rows=log_rows, findings=list(findings)), findings
    return database, findings + _persist(database, hook, log_rows, findings)


def fire(hook: str, database, *, rules=None, templates=None, params=None,
         files_root=None, hooks=None) -> tuple:
    """Fire every rule registered for `hook` (CSV order) and return (database, findings).

    `database` may be None for a hook where no staged Database exists (before_300): add_rows rules
    then produce a located finding, file rules still run, and - when the hook had business - the
    first element returned is a `Deferred` (hand it to `settle` once a database exists) instead of
    None. Defaults come from the active config: rules/templates via the 4-tier resolver,
    `files_root` = the project output root. `hooks` = every hook the calling run-plan fires: a
    rule naming any other hook would never fire, so it is reported (`rx_unfired_hook`).

    STRICT NO-OP when the hook has nothing to do - no rule for it (valid or malformed) and no
    rule-INDEX problem (a malformed row naming no hook, a rule on a hook nobody fires, an unreadable
    rules file): beyond the rule index itself nothing loads, nothing writes, nothing logs - the
    empty-config byte-parity guarantee. Index-wide problems are every hook's business: rendered at
    each fire, recorded once (uid dedupe)."""
    hook = hook.strip().lower()
    if isinstance(rules, list) and rules and isinstance(rules[0], Rule):
        compiled, tagged = list(rules), []
    else:
        if rules is None:
            rules, problem = _load(config.load_reactions, "rx_rules_unreadable", RULES_FILE)
            if problem is not None:      # a broken rule index is every hook's business - never silent
                return _finish(hook, database, [], [problem])
        compiled, tagged = _compile(rules)
    if hooks is not None:                # the run-plan's own hooks: a rule anywhere else never fires
        declared = [h.strip().lower() for h in hooks]   # the run-plan's firing order (for the message)
        fired = set(declared)
        tagged = [(owner if owner in fired else None, finding) for owner, finding in tagged]
        for rule in compiled:
            if rule.fire_when not in fired:
                tagged.append((None, _f(rule.phase, "rx_unfired_hook",
                                        f"hook {rule.fire_when!r} is never fired by this run-plan "
                                        f"(it fires: {', '.join(declared)})", rule.name)))
        compiled = [r for r in compiled if r.fire_when in fired]
    findings = [finding for _owner, finding in tagged]
    active = [r for r in compiled if r.fire_when == hook]
    concerns = [finding for owner, finding in tagged if owner in (hook, None)]
    if not active and not concerns:      # the no-op fast path: beyond the rule index itself, nothing
        return database, findings        # further loads, nothing writes, nothing logs (another hook's
                                         # malformed rule still surfaces - it is recorded at its own)
    blocked = None
    if active:
        if templates is None:
            templates, blocked = _load(config.load_reaction_templates, "rx_templates_unreadable",
                                       TEMPLATES_FILE)
        if params is None and blocked is None:
            params, blocked = _load(config.load_params, "rx_params_unreadable", "project_params.yaml")
        if blocked is not None:
            findings.append(blocked)
    files_root = config.output_root() if files_root is None else files_root
    db_tables = _db_tables(database) if database is not None and active else {}

    log_rows = []
    for rule in active:
        matched, problems, tally = [], [], {"created": 0}
        if blocked is None:
            try:
                reason = _template_problem(rule, templates)
                if reason:
                    problems = [_f(rule.phase, "rx_bad_template", reason, rule.name)]
                else:
                    matched, problem = _matches(rule, database, params, db_tables)
                    if problem is not None:
                        problems = [problem]
                    elif rule.action == "add_rows":
                        problems = _spawn_rows(rule, matched, database, templates, params, db_tables, tally)
                    else:
                        problems = _append_file(rule, matched, templates, params, db_tables, files_root, tally)
            except Exception as error:   # the backstop: an unforeseen defect is a finding, never a crash
                problems = [_f(rule.phase, "rx_rule_crashed", f"{type(error).__name__}: {error}", rule.name)]
        findings.extend(problems)
        outcome = blocked.type if blocked is not None else (problems[0].type if problems else "ok")
        log_rows.append({"hook": rule.fire_when, "rule": rule.name, "action": rule.action,
                         "target": rule.target, "matches": len(matched), "created": tally["created"],
                         "outcome": outcome})
    return _finish(hook, database, log_rows, findings)
