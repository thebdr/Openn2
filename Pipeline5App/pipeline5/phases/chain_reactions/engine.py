"""The chain-reaction RULE ENGINE - compile the config rules, match, spawn/append, audit, `fire`.

WHERE YOU MEET IT: a system's run-plan fires hooks around its phase work (Siemens:
src://pipeline5/systems/plc_based/siemens_s7/safety/main.py fires `before_300`/`after_300` around
the staging leg), so a phase button and Run-all trigger reactions identically. With no rules
configured for a hook, `fire` is a strict NO-OP - it touches neither the Database nor the disk
(the byte-parity guarantee: an empty rule set changes nothing).

THE RULE (one row of `chain_reactions/reactions.csv` - per-system config, 4-tier resolved):

    name          the rule's id - lands in the log + in every spawned row's `spawned_by`
    fire_when     `before_<phase>` / `after_<phase>` (e.g. after_300) - which hook fires it
    source_table  the SSOT table whose rows are tested; EMPTY = fire ONCE with an empty row scope
                  (a source-less file rule, e.g. a generated-file header)
    condition     an expr predicate run per source row (empty = every row matches)
    action        `add_rows` - spawn rows into an SSOT table | `file` - render + APPEND to a file
    target        add_rows: the target TABLE name | file: the file path (an expr template,
                  rendered per match; relative paths land under the project output root)
    template      the templates.yaml entry: add_rows needs a ROW template (a list of
                  {field: expr-template} dicts - one spawned row per entry per match);
                  file needs a TEXT template (src://pipeline5/language/tempemplator.py)
    comment       free text for the reader

THE SCOPE an expression sees (the E1 layering): the matched source row's fields at top level,
`_params` = the project params (dotted: {$_params.project.name}), `_rule` = {name, hook},
`_db` = every SSOT table (expr's data functions + the @for table queries read it).

APPEND is the file action's ONLY mode (user decision 2026-07-16): the file is created if absent and
APPENDED otherwise - the USER is responsible for lifecycle handling (e.g. a `before_<phase>` rule
that opens a fresh header, or deleting the file between runs). The audit trail is the
`chain_reactions_log` SSOT table: one row per rule firing (hook, rule, action, target, match count,
rows-or-lines created), REPLACED per hook on each firing so the Explorer shows the LAST run.

FAILURES ARE FINDINGS, NEVER SILENT (and never a crash): a malformed rule, an unknown table, a bad
expression, a template error - each becomes a located ERRR finding (the rule is skipped, the run
continues; ERRR = possibly-incomplete output, per the severity contract) rendered through the
handler's `ctx.render` and recorded to `validation_issues`.

KNOWN BOUNDARY (deliberate, until the generated-signals spec review): an `after_300` `add_rows`
spawn persists into the SAVED Database - visible in the Explorer - but downstream phases RE-STAGE
from the source document, so spawned `signals` rows do not yet flow into generation. The flagship
absorption (spawned signals consumed by every phase) lands with its own reviewed step.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

from pipeline5 import config
from pipeline5.findings.finding import Finding, record
from pipeline5.language import expr
from pipeline5.language import tempemplator
from pipeline5.language.expr import ExprError
from pipeline5.language.tempemplator import TempemplatorError
from pipeline5.truth.table import Table

_HOOK = re.compile(r"^(before|after)_(\d+)$")
_ACTIONS = ("add_rows", "file")

LOG_TABLE = "chain_reactions_log"


def chain_reactions_log_table() -> Table:
    """The audit-trail SSOT table: one row per rule firing at its hook (see the module chapter)."""
    return Table(LOG_TABLE,
                 columns=["uid", "hook", "rule", "action", "target", "matches", "created"],
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


def _f(phase: int, type_: str, detail: str, location: str) -> Finding:
    return Finding(phase=phase, type=type_, severity="ERRR", detail=detail, location=location)


def compile_rules(rows) -> tuple:
    """reactions.csv rows -> (rules, findings). A malformed row becomes a located ERRR finding and
    is DROPPED (the engine never fires a rule it could not validate)."""
    rules, findings = [], []
    for row in rows:
        name = (row.get("name") or "").strip()
        fire_when = (row.get("fire_when") or "").strip().lower()
        action = (row.get("action") or "").strip().lower()
        target = (row.get("target") or "").strip()
        template = (row.get("template") or "").strip()
        hook = _HOOK.match(fire_when)
        problems = []
        if not hook:
            problems.append(f"fire_when {fire_when!r} is not before_<phase>/after_<phase>")
        if action not in _ACTIONS:
            problems.append(f"action {action!r} is not one of {_ACTIONS}")
        if not target:
            problems.append("target is empty (a table name or a file path)")
        if not template:
            problems.append("template is empty (a templates.yaml entry name)")
        if problems:
            phase = int(hook.group(2)) if hook else 0
            findings.append(_f(phase, "rx_bad_rule", "; ".join(problems), name or "<unnamed rule>"))
            continue
        rules.append(Rule(name=name, fire_when=fire_when,
                          source_table=(row.get("source_table") or "").strip(),
                          condition=(row.get("condition") or "").strip(),
                          action=action, target=target, template=template,
                          comment=(row.get("comment") or "").strip()))
    return rules, findings


def _scope(row: dict, rule: Rule, params: dict, db_tables: dict) -> dict:
    """The E1 layered expression scope for one matched row (see the module chapter)."""
    return {**row, "_params": params, "_rule": {"name": rule.name, "hook": rule.fire_when},
            "_db": db_tables}


def _matches(rule: Rule, database, params: dict, db_tables: dict) -> tuple:
    """The source rows the rule fires for: (rows, finding_or_None). No source_table -> ONE empty
    row (a fire-once rule). Bad table / bad condition -> the located finding, rule skipped."""
    if not rule.source_table:
        candidates = [{}]
    else:
        if database is None or rule.source_table not in database:
            return [], _f(rule.phase, "rx_unknown_table",
                          f"source table {rule.source_table!r} is not in the database at this hook",
                          rule.name)
        candidates = [dict(r) for r in database[rule.source_table]]
    if not rule.condition:
        return candidates, None
    try:
        return [r for r in candidates
                if expr.test(rule.condition, _scope(r, rule, params, db_tables))], None
    except ExprError as error:
        return [], _f(rule.phase, "rx_bad_condition", str(error), rule.name)


def _spawn_rows(rule: Rule, matched: list, database, templates: dict,
                params: dict, db_tables: dict) -> tuple:
    """The add_rows action: per matched row, per row-spec of the ROW template, spawn one expr-filled
    row into the target table WITH provenance (spawned_by = the rule, source_uid = the trigger).
    Returns (created_count, findings)."""
    if database is None or rule.target not in database:
        return 0, [_f(rule.phase, "rx_unknown_table",
                      f"target table {rule.target!r} is not in the database at this hook", rule.name)]
    spec = templates.get(rule.template)
    if not isinstance(spec, list):
        return 0, [_f(rule.phase, "rx_bad_template",
                      f"template {rule.template!r} is not a ROW template (a list of field maps)",
                      rule.name)]
    table = database[rule.target]
    created = 0
    for row in matched:
        scope = _scope(row, rule, params, db_tables)
        for row_spec in spec:
            try:
                values = {str(field): expr.render(str(tpl), scope, mode="strict")
                          for field, tpl in dict(row_spec).items()}
            except ExprError as error:
                return created, [_f(rule.phase, "rx_bad_template",
                                    f"row template {rule.template!r}: {error}", rule.name)]
            values["spawned_by"] = rule.name
            values.setdefault("source_uid", str(row.get("uid") or ""))
            table.add(**values)
            created += 1
    return created, []


def _append_file(rule: Rule, matched: list, templates: dict, params: dict,
                 db_tables: dict, files_root: str) -> tuple:
    """The file action: per matched row, render the TEXT template and APPEND it (+ newline) to the
    expr-rendered target path (relative -> under `files_root`). Returns (lines_written, findings)."""
    written = 0
    for row in matched:
        scope = _scope(row, rule, params, db_tables)
        try:
            path = expr.render(rule.target, scope, mode="strict")
            text = tempemplator.render_template(rule.template, templates, scope)
        except (ExprError, TempemplatorError) as error:
            return written, [_f(rule.phase, "rx_bad_template", str(error), rule.name)]
        if not os.path.isabs(path):
            path = os.path.join(files_root, path)
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:      # APPEND is the only mode (user decision)
            handle.write(text + "\n")
        written += text.count("\n") + 1
    return written, []


def fire(hook: str, database, *, rules=None, templates=None, params=None,
         files_root=None) -> tuple:
    """Fire every rule registered for `hook` (CSV order) and return (database, findings).

    `database` may be None for hooks where no staged Database exists (a before-hook); add_rows
    rules then produce a located finding, file rules still run. Defaults come from the active
    config: rules/templates via the 4-tier resolver, `files_root` = the project output root.
    STRICT NO-OP when the hook has no rules: nothing loaded further, nothing written, nothing
    logged - the empty-config byte-parity guarantee."""
    compiled, findings = (rules, []) if isinstance(rules, list) and rules and isinstance(rules[0], Rule) \
        else compile_rules(config.load_reactions() if rules is None else rules)
    active = [r for r in compiled if r.fire_when == hook.strip().lower()]
    if not active:                       # the no-op fast path: beyond the rule index itself, nothing
        return database, findings        # further loads, nothing writes, nothing logs (compile
                                         # findings still surface - a malformed rule is never silent)

    templates = config.load_reaction_templates() if templates is None else templates
    params = config.load_params() if params is None else params
    files_root = config.output_root() if files_root is None else files_root
    db_tables = {name: list(database[name]) for name in database.names()} if database is not None else {}

    log_rows = []
    for rule in active:
        matched, problem = _matches(rule, database, params, db_tables)
        if problem is not None:
            findings.append(problem)
            continue
        if rule.action == "add_rows":
            created, action_findings = _spawn_rows(rule, matched, database, templates, params, db_tables)
        else:
            created, action_findings = _append_file(rule, matched, templates, params, db_tables, files_root)
        findings.extend(action_findings)
        log_rows.append({"hook": rule.fire_when, "rule": rule.name, "action": rule.action,
                         "target": rule.target, "matches": len(matched), "created": created})

    if log_rows and database is not None:
        log = database[LOG_TABLE] if LOG_TABLE in database else database.add_table(chain_reactions_log_table())
        log.rows = [r for r in log.rows if r.get("hook") != hook]   # this hook's audit reflects THE LAST run
        log.extend(log_rows)
        if findings:
            record(database, findings)
        database.save(config.database_dir())
    return database, findings
