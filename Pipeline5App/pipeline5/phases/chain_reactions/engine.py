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
phases fill, yet the renderer's loop-column check must see the table's real schema. Rules fire in
CSV order and `_db` is REBUILT after a rule spawns rows, so a later rule sees the spawns exactly as
its matching does (the chain reaction within one hook - refuter round 9).

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
    rx_file_write       the rendered target path cannot be written as the file it names (e.g. a
                        Windows-invalid `"`, a ':' in the file name - NTFS would hide the text in an
                        alternate data stream - a device name like `NUL`: see `_path_refusal`)
    rx_rules_unreadable / rx_templates_unreadable / rx_params_unreadable
                        a config file does not load (e.g. a YAML syntax error) - the hook's rules
                        are all blocked, each audited with that outcome
    rx_unfired_hook     a rule on a hook the run-plan never fires (it would never run) - dropped
    rx_record_unreadable / rx_record_unwritable
                        the reaction record (audit / validation_issues) does not load - a hand-edited
                        CSV gone ragged: left UNTOUCHED, nothing recorded over it, while the rest of
                        the Database (a spawn) is still saved - or does not save (a file held open,
                        e.g. by Excel; a value the CSV cannot store); rendered, never a crash
    rx_rule_crashed     the backstop - an unforeseen defect, reported with its exception type

A problem of the rule INDEX itself (a row naming no hook, an unfired hook, an unreadable
reactions.csv) belongs to no single hook: it is every hook's business - rendered at each fire,
recorded once (the file-level findings carry phase 0, so the uid is the same whichever hook - and
whichever PHASE - meets the file). A HALTED staging commits no reaction record (the run-plan lists the deferred
before_300 firings in the log instead - a half-committed record would mix runs).

THE TEMPLATE BUILDER (C-025 - the Files tab's templates.yaml mode) reads the engine through
side-effect-free doors: `lint(templates, rule, database, hooks)` - what a fire would report, found
WITHOUT firing (every branch of every template; with a chosen rule, its E1 scope and its hook's
tables) - and `preview(rule, row_index, ...)` - one fire for one source row through the fire path's
OWN guards and render steps (the hook check, the backstop, `_spawned`, `_file_output`), nothing
added, nothing written. The Database a preview renders over is the one the fire GETS: the system's
declared hook loader (the run-plan's own input, rebuilt in memory), a settled database-less hook
(`has_business` / `settle_view`), and the in-hook chain reaction (`cascade`, through the fire's own
per-rule step `_act`) - modelled by the builder's Session (src://pipeline5/workbench/template_doc.py).

KNOWN BOUNDARY (deliberate, until the generated-signals spec review): an `after_300` `add_rows`
spawn persists into the SAVED Database - visible in the Explorer - but downstream phases RE-STAGE
from the source document, so spawned `signals` rows do not yet flow into generation. The flagship
absorption (spawned signals consumed by every phase) lands with its own reviewed step.
"""
from __future__ import annotations

import itertools
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
_WINDOWS = os.name == "nt"
# the characters a Windows file path refuses (open() -> EINVAL): judged BEFORE the write, so the fire and
# the builder's preview name the same refusal (C-025 refute round 2); other platforms accept them
_INVALID_PATH = '<>"|?*' if _WINDOWS else ""
_SEPARATORS = ("\\", "/")
_STRICT = "\\\\?\\"      # the device prefix Win32 takes AS WRITTEN - no '/' separator, no '.' / '..' resolved
# a Win32 DEVICE-path prefix in every spelling Win32 reads as one: two separators, '.' or '?', a separator
_DEVICE_PREFIXES = tuple(a + b + mark + c for a in _SEPARATORS for b in _SEPARATORS for mark in ".?"
                         for c in _SEPARATORS)
_TWO_SEPARATORS = tuple(a + b for a in _SEPARATORS for b in _SEPARATORS)
# the names Windows opens as a DEVICE - older Windows whatever the extension (`NUL.txt`): the text would go to
# the device, not to a file (C-024 refute round 22's note: `rx/NUL` audited "ok", nothing on disk)
_DEVICE_NAMES = frozenset(["CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"]
                          + [port + digit for port in ("COM", "LPT") for digit in "0123456789\u00b9\u00b2\u00b3"])


class WouldNotFire(Exception):
    """A system's hook loader (System.reaction_hooks) found that the run-plan halts BEFORE the hook
    fires - e.g. a staging FAIL the treatments registry does not lift. The builder says so instead of
    previewing a fire that never happens."""

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
    """A located ERRR finding, its text as the record can store it: a lone surrogate the message quotes (half
    of a YAML `\\uD83D\\uDE00` escape pair - a duplicate key's value, a malformed /regex/, an @use cycle's
    names) escaped - the finding's uid hashes UTF-8 and validation_issues.csv stores it (C-024 refute round
    22: the raw text crashed the run at the record)."""
    return Finding(phase=phase, type=type_, severity="ERRR", detail=_storable(detail), location=_storable(location))


def _storable(text) -> str:
    """`text` with every lone surrogate escaped (`\\ud83d`) - UTF-8 stores any other character as it is."""
    return str(text).encode("utf-8", "backslashreplace").decode("utf-8")


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
    return _row_template_problem(rule.template, body)


def _row_template_problem(name: str, body):
    """Why `body` cannot serve add_rows (None = it can): a non-empty list of {field: template STRING}
    maps - the fire path's check, and the builder's lint of every row template."""
    if not isinstance(body, list) or not body:
        return f"template {name!r} is not a ROW template (a non-empty list of field maps)"
    for number, spec in enumerate(body, start=1):
        if not isinstance(spec, dict) or not spec:
            return f"row template {name!r} entry {number} is not a {{field: expr}} map"
        for column, value in spec.items():
            if not isinstance(column, str):                  # YAML typed the NAME (`010:` reads as 10, `true:` as
                return (f"row template {name!r} entry {number}: the field name {column!r} is a "   # True): it would
                        f"{type(column).__name__}, not a text - YAML typed it; quote it")          # be renamed
            unstorable = _unencodable(str(column))           # a column name: the CSV header (round 22 -
            if unstorable:                                   # the save failed after the add, the table's
                return (f"row template {name!r} entry {number}: the field name {str(column)!r}: "  # CSV
                        f"{unstorable}")                                                         # emptied)
            if value is None:
                return (f"row template {name!r} entry {number}: field {column!r} has no "
                        "value (write '' for an empty field)")
            if not isinstance(value, str):                   # YAML typed it: a list would be stored as
                return (f"row template {name!r} entry {number}: field {column!r} is a "  # its repr,
                        f"{type(value).__name__} ({value!r}), not a template string - quote it")  # 007 as 7
    return None


def _unknown_table(role: str, table: str) -> str:
    return f"{role} table {table!r} is not in the database at this hook"


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
            return [], _f(rule.phase, "rx_unknown_table", _unknown_table("source", rule.source_table),
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
        return [_f(rule.phase, "rx_unknown_table", _unknown_table("target", rule.target), rule.name)]
    table = database[rule.target]
    for row in matched:
        try:
            for values in _spawned(rule, templates, _scope(row, rule, params, db_tables), row):
                table.add_row(values)                          # added as rendered: a later spec's failure
                tally["created"] += 1                          # keeps the true partial count
        except ExprError as error:
            return [_f(rule.phase, "rx_bad_template", _bad_rows(rule, error), rule.name)]
    return []


def _spawned(rule: Rule, templates: dict, scope: dict, row: dict):
    """Yield the rows ONE matched source row spawns - one per row spec, rendered (strict), NOT added;
    a value that fails raises ExprError at its spec. The fire adds each as it comes; the preview
    collects them."""
    for number, row_spec in enumerate(templates[rule.template], start=1):
        values = {}
        for name, tpl in row_spec.items():
            try:
                values[str(name)] = tempemplator.render_text(str(tpl), scope)
            except ExprError as error:                     # located: which entry, which field
                raise ExprError(f"entry {number} field {str(name)!r}: {error}") from error
            unstorable = _unencodable(values[str(name)])   # refused BEFORE the add (its uid, the save)
            if unstorable:
                raise ExprError(f"entry {number} field {str(name)!r}: {unstorable}")
        values["spawned_by"] = rule.name
        values.setdefault("source_uid", str(row.get("uid") or ""))
        yield values


def _bad_rows(rule: Rule, error) -> str:
    return f"row template {rule.template!r}: {error}"


def _append_file(rule: Rule, matched: list, templates: dict, params: dict,
                 db_tables: dict, files_root: str, tally: dict, write: bool = True) -> list:
    """The file action: per matched row, render the TEXT template and APPEND it (+ newline) to the
    expr-rendered target path (relative -> under `files_root`). Counts the lines written into
    `tally["created"]` as it goes. Returns the findings. `write` False = a DRY fire: every step but
    the write itself (counted as written)."""
    for row in matched:
        path, text, problem = _file_output(rule, templates, _scope(row, rule, params, db_tables), files_root)
        if problem is not None:
            return [_f(rule.phase, *problem, rule.name)]
        if write:
            try:
                os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
                with open(path, "a", encoding="utf-8") as handle:  # APPEND is the only mode (user decision)
                    handle.write(text + "\n")
            except OSError as error:                               # e.g. a file held open, a permission
                return [_f(rule.phase, "rx_file_write", f"cannot write {path!r}: {error.strerror or error}",
                           rule.name)]
        tally["created"] += text.count("\n") + 1
    return []


def _file_output(rule: Rule, templates: dict, scope: dict, files_root: str) -> tuple:
    """ONE matched row's file output as a fire makes it - rendered (strict) and guarded, NOT written:
    (path, text, None), or (None, None, (finding type, detail)) when the fire would refuse it."""
    try:
        path = tempemplator.render_text(rule.target, scope)
    except ExprError as error:                                     # the holes render one by one - so
        return None, None, ("rx_bad_template", f"target {rule.target!r}: {error}")   # name the target
    try:
        text = tempemplator.render_template(rule.template, templates, scope)
    except (ExprError, TempemplatorError) as error:
        return None, None, ("rx_bad_template", str(error))
    judged = path                                                  # the TARGET's own names are judged, never the
    # output root's (Windows 11 allows `aux.files`). Rooted without a drive (`/rx/a.txt`): joined, it lands at the
    # ROOT of the output root's drive - refused before any isabs test (Python < 3.13 calls it absolute: never
    # joined, it was written at the root of the current drive)
    if _WINDOWS and path[:1] in _SEPARATORS and path[1:2] not in _SEPARATORS:
        return None, None, ("rx_file_write", f"cannot write {path!r}: a path rooted without a drive lands at the "
                            "root of the output root's drive - write the drive, or a relative path")
    if not os.path.isabs(path):
        if ":" in path:                                            # `X:3.txt` would read as drive X: (a
            return None, None, ("rx_file_write",                   # drive-relative escape - round 14)
                                f"cannot write {path!r}: a ':' in a relative target (a drive letter, or a "
                                "hidden NTFS stream) - use an absolute path for another drive")
        path = os.path.join(files_root, path)
    refusal = _path_refusal(judged)
    if refusal is not None:                                        # Windows refuses it at open() - say why
        return None, None, ("rx_file_write", f"cannot write {path!r}: {refusal}")
    colon = _colon_name(judged)                                    # NTFS would write a HIDDEN alternate data
    if colon is not None:                                          # stream - silent (refuter round 13: a `-X1:3`
        return None, None, ("rx_file_write", f"cannot write {path!r}: a ':' in the name {colon!r} would write a "
                            "hidden NTFS stream")                  # terminal name) - judged AS WRITTEN (C-025 round 6)
    unstorable = _unencodable(text)                                # the append would fail half-way
    if unstorable:
        return None, None, ("rx_bad_template", f"template {rule.template!r}: {unstorable}")
    return path, text, None


def _path_refusal(path: str):
    """Why Windows would not write `path` as the file it names - judged BEFORE the write, so the fire, its dry
    run and the builder name the same refusal (None = none; other platforms take any of these). A relative
    target is judged as written - its own names, never the output root's it joins (Windows 11 allows a
    folder `aux.files`); the lint reads the same text:
    - a character a path refuses (`<>"|?*`, a control character) anywhere past a device prefix (`\\\\?\\`,
      `//./` - any mix of separators, as Win32 reads it) - its drive and a UNC share included;
    - a drive that is not ONE ASCII letter (`1:`, `é:`); a device path's drive going on without a separator
      (`\\\\?\\C:x`, drive-relative);
    - a `\\\\?\\` path (Win32 takes it AS WRITTEN): a '/', or a '.' / '..' / empty name;
    - a device path naming no drive, share (`UNC`) or volume (`Volume{...}`) - a pipe, a raw device - or one
      whose '..' climbs above its drive / share (Win32 would drop the drive);
    - a path naming no file (it ends in a separator, '.' or '..');
    - a name ending in '.' or ' ' (Windows drops them - another file, or none, would be written);
    - a device name (`NUL`, `CON`, `COM1`, ... - older Windows whatever the extension, `NUL.txt`)."""
    if not _WINDOWS:
        return None
    prefix = _device_prefix(path)
    strict = path.startswith(_STRICT)
    body = path[prefix:]
    bad = next((ch for ch in body if ch in _INVALID_PATH or ord(ch) < 32), None)
    if bad is not None:
        return f"{bad!r} is not allowed in a Windows path"
    if strict and "/" in body:
        return f"'/' is not a separator in a {_STRICT} path (Windows takes it as written) - write '\\'"
    if body[1:2] == ":":
        if not (body[:1].isascii() and body[:1].isalpha()):
            return f"{body[:2]!r} is not a drive"
        if prefix and body[2:3] not in _SEPARATORS:
            return f"a device path's drive {body[:2]!r} must go on with a separator"
    names = body.split("\\") if strict else re.split(r"[\\/]", body)
    if names[-1] in ("", ".", ".."):
        return "the target names a folder, not a file (it ends in a separator, '.' or '..')"
    unc = not prefix and body[:1] in _SEPARATORS and body[1:2] in _SEPARATORS   # \\server\share\...
    volume = _volume_depth(names[0]) if prefix else 2 if unc else 0
    if volume is None:
        return (f"a device path's first name is its drive ({_STRICT}C:\\), share ({_STRICT}UNC\\) or volume - "
                f"{names[0]!r} is none of them (a pipe, a raw device - an empty, '.' or '..' name there included)")
    for name in names:
        refusal = _name_refusal(name, strict)
        if refusal:
            return refusal
    if prefix or unc:
        depth, climb = _depth(names[2:] if unc else names, volume, device=bool(prefix))
        if climb is not None:
            return f"'..' climbs above the device path's {'share' if volume > 1 else 'drive'} (Windows drops it)"
        if depth <= volume:
            return f"the target names a {'server or a share' if unc else 'drive or a share'}, not a file"
    return None


def _depth(names: list, volume: int, device: bool) -> tuple:
    """(how deep `names` reach, the index of a '..' that climbs above the first `volume` of them - None: none does).
    As Win32 walks them: an empty or '.' name is no step, '..' one up - above a device path's volume it drops the
    drive / share (refused), at a UNC path's share it stays (Win32 clamps there, as at a drive's root). The share
    root of a device or UNC path in any spelling (`\\\\.\\UNC\\srv\\.\\share`) reaches no deeper than its volume: no file
    (C-024 refute round 23, F2)."""
    depth, climb = 0, None
    for index, name in enumerate(names):
        if name in ("", "."):
            continue
        if name != "..":
            depth += 1
        elif depth > volume:
            depth -= 1
        elif device and climb is None:
            climb = index
    return depth, climb


def _colon_name(path: str):
    """The first name of `path` holding a ':' past its drive - judged AS WRITTEN: a `..` after it removes nothing
    (the lint reads the same text), a UNC server / share and a volume name included. None: there is none."""
    body = path[_device_prefix(path):] if _WINDOWS else path
    names = re.split(r"[\\/]", body) if _WINDOWS else body.split("/")
    drive = 1 if _WINDOWS and names[0][1:2] == ":" else 0          # (the drive's own ':' - `_path_refusal` judges it)
    return next((name for name in names[drive:] if ":" in name), None)


def _device_prefix(path: str) -> int:
    """The length of the Win32 DEVICE-path prefix `path` opens with (0 = none): two separators, '.' or '?', a
    separator - in any mix of '\\' and '/' (`\\\\.\\`, `//?/`, `\\\\./`: Win32 reads each as one)."""
    return 4 if path[:4] in _DEVICE_PREFIXES else 0


def _volume_depth(head: str):
    """How many names a device path's volume takes - a drive `C:` or a `Volume{...}` 1, a share `UNC\\srv\\share` 3;
    None: `head` names none of them."""
    if head.upper() == "UNC":
        return 3
    if (len(head) == 2 and head[1] == ":" and head[0].isascii() and head[0].isalpha()) \
            or (head[:7].upper() == "VOLUME{" and head.endswith("}")):
        return 1
    return None


def _name_refusal(name: str, strict: bool):
    """Why Windows would not write the path name `name` as it is written (None = it would) - see
    `_path_refusal`. `strict`: a `\\\\?\\` path's name."""
    if name in ("", ".", ".."):
        if strict:
            return (f"a {_STRICT} path resolves no '.' / '..' and takes no empty name - {name!r} "
                    "(Windows takes it as written)")
        return None
    if name[-1] in (".", " "):
        return (f"the name {name!r} ends in {name[-1]!r} - Windows drops it (another file, or none, "
                "would be written)")
    if re.split(r"[.:]", name, maxsplit=1)[0].rstrip(" ").upper() in _DEVICE_NAMES:   # `NUL.txt`, `NUL:`
        return f"{name!r} is a Windows device name - the text would go to the device, not to a file"
    return None


def _unencodable(text: str):
    """Why `text` cannot be stored as UTF-8 (a lone surrogate - a YAML `\\uD83D\\uDE00` escape pair decodes
    to two) - None when it can."""
    try:
        text.encode("utf-8")
    except UnicodeEncodeError as error:
        return (f"{text[error.start]!r} (a lone surrogate) cannot be stored as UTF-8 - write the character "
                "itself, not a \\uXXXX surrogate pair")
    return None


def _act(rule: Rule, database, templates: dict, params: dict, db_tables: dict, files_root: str,
         tally: dict, write: bool = True) -> tuple:
    """ONE rule's turn at its hook - the template check, the matching, then the spawn / the append -
    with the per-rule BACKSTOP: an unforeseen exception anywhere in it is `rx_rule_crashed`, never a
    crash. Returns (matched rows, problems); `tally["created"]` counts as it goes. The fire's step,
    and the builder's `cascade`. `write` False: a file rule writes nothing (a dry fire)."""
    matched = []
    try:
        reason = _template_problem(rule, templates)
        if reason:
            return [], [_f(rule.phase, "rx_bad_template", reason, rule.name)]
        matched, problem = _matches(rule, database, params, db_tables)
        if problem is not None:
            return matched, [problem]
        if rule.action == "add_rows":
            return matched, _spawn_rows(rule, matched, database, templates, params, db_tables, tally)
        return matched, _append_file(rule, matched, templates, params, db_tables, files_root, tally, write)
    except Exception as error:   # the backstop: an unforeseen defect is a finding, never a crash
        return matched, [_f(rule.phase, "rx_rule_crashed", f"{type(error).__name__}: {error}", rule.name)]


def _unfired(hook: str, declared) -> str:
    return f"hook {hook!r} is never fired by this run-plan (it fires: {', '.join(declared)})"


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


_RECORD = ((LOG_TABLE, chain_reactions_log_table), ("validation_issues", validation_issues_table))


def _attach_record(database, directory: str) -> None:
    """Attach the reaction-record tables (the audit + validation_issues) this Database never loaded -
    from the ON-DISK record (the 310 leg stages only signals + diagnosis_cabinets), so appending and
    saving never overwrite what earlier phases recorded (refuter round 7). BOTH load or NEITHER is
    attached: a table that fails to load must never half-attach, since whatever is attached is saved
    (refuter round 9). Raises when a record file does not load."""
    missing = [(name, factory) for name, factory in _RECORD if name not in database]
    if missing:
        loaded = Database([factory() for _name, factory in missing]).load(directory)
        for name, _factory in missing:
            database.add_table(loaded[name])


def _record_new(database, findings) -> int:
    """Record the findings not yet in `validation_issues` (by uid - a malformed rule surfaces at every
    hook's fire, but lands in the record ONCE). Returns the count recorded; the caller saves."""
    known = {r.get("uid") for r in database["validation_issues"]}
    fresh = []
    for finding in findings:
        if finding.uid not in known:
            known.add(finding.uid)
            fresh.append(finding)
    if fresh:
        record(database, fresh)
    return len(fresh)


def _persist(database, hook: str, log_rows: list, findings: list, save: bool = True) -> list:
    """Replace `hook`'s audit rows with this firing's, record its findings, save the database. A record
    that will not LOAD (a hand-edited CSV gone ragged) is left untouched - this firing's audit and
    findings are not recorded over it - yet the REST of the Database is still saved (an add_rows spawn
    must not vanish with it - refuter round 9); one that will not SAVE (a file held open, e.g. by
    Excel) is reported. Either is a located finding, never a crash (refuter round 8). Returns those
    findings for the caller to surface."""
    phase, where = _hook_phase(hook), config.database_dir()
    problems = []
    try:
        _attach_record(database, where)
    except Exception as error:
        problems.append(_f(phase, "rx_record_unreadable",
                           "the reaction record does not load - left untouched: this firing's audit and "
                           f"findings were NOT recorded (the rest of the Database was saved): {error}", where))
    else:
        log = database[LOG_TABLE]
        log.rows = [r for r in log.rows if r.get("hook") != hook]   # this hook's audit reflects THE LAST run
        log.extend(log_rows)
        _record_new(database, findings)
    if not save:                                              # the builder's view of a settle: attached +
        return problems                                       # recorded in memory, nothing written
    try:
        database.save(where)
    except (OSError, ValueError) as error:                   # a file held open; a value a CSV cannot store
        cause = "a file held open by another program?" if isinstance(error, OSError) else "a value the CSV cannot store"
        problems.append(_f(phase, "rx_record_unwritable", f"the record could not be saved ({cause}): {error}", where))
    return problems


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
         files_root=None, hooks=None, write: bool = True) -> tuple:
    """Fire every rule registered for `hook` (CSV order) and return (database, findings).

    `database` may be None for a hook where no staged Database exists (before_300): add_rows rules
    then produce a located finding, file rules still run, and - when the hook had business - the
    first element returned is a `Deferred` (hand it to `settle` once a database exists) instead of
    None. Defaults come from the active config: rules/templates via the 4-tier resolver,
    `files_root` = the project output root. `hooks` = every hook the calling run-plan fires: a
    rule naming any other hook would never fire, so it is reported (`rx_unfired_hook`). `write`
    False = a DRY fire (the template builder's model of a settle): every step - the audit rows and
    findings a real fire gives - but a file rule writes nothing (only a write the OS itself would
    refuse is beyond it).

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
                tagged.append((None, _f(rule.phase, "rx_unfired_hook", _unfired(rule.fire_when, declared),
                                        rule.name)))
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
            matched, problems = _act(rule, database, templates, params, db_tables, files_root, tally, write)
        if rule.action == "add_rows" and tally["created"]:
            db_tables = _db_tables(database)                 # the CASCADE: a later rule's `_db` sees this
        findings.extend(problems)                            # rule's spawns, as its matching does (round 9)
        outcome = blocked.type if blocked is not None else (problems[0].type if problems else "ok")
        log_rows.append({"hook": rule.fire_when, "rule": rule.name, "action": rule.action,
                         "target": rule.target, "matches": len(matched), "created": tally["created"],
                         "outcome": outcome})
    return _finish(hook, database, log_rows, findings)


# --- the template builder's doors (P-012) - side-effect free ------------------------------------- #
@dataclass
class Preview:
    """What a fire of a rule would do for ONE source row - produced by the fire path's own render steps,
    nothing added, nothing written (the template builder's live preview)."""
    matched: bool | None = True     # the condition holds (a fire acts on the row) / fails (a fire skips
                                    # it) / None: the fire stops BEFORE the condition (a problem)
    rows: list = field(default_factory=list)    # add_rows: the rows it would spawn (provenance incl.)
    path: str = ""                  # file: the file it would APPEND to
    text: str = ""                  # file: the text it would append
    problem: tuple | None = None    # (finding type, detail): what the fire would report instead
    note: str = ""                  # a preview-only remark (e.g. the source table has no rows)

    def __post_init__(self):
        if self.problem is not None:                      # the detail as the fire's finding carries it (`_f`)
            self.problem = (self.problem[0], _storable(self.problem[1]))


def db_layer(database) -> dict:
    """The E1 `_db` layer a fire builds over `database` ({} for none) - {table: its complete rows}.
    The builder computes it ONCE per hook and hands it to every `preview` (it re-previews on each
    edit; the data does not change between edits, and a 20k-row layer costs a noticeable 0.3 s)."""
    return _db_tables(database) if database is not None else {}


def preview(rule: Rule, row_index: int = 0, *, templates: dict, params: dict, database,
            files_root: str | None = None, layer: dict | None = None, hooks=None) -> Preview:
    """ONE fire of `rule` for the source row at `row_index` of its hook's `database` (None = a
    database-less hook; a source-less rule previews its single fire): the fire's own guards - a hook
    the run-plan never fires (`hooks`), the per-rule backstop (rx_rule_crashed) - then
    `_template_problem`, `_scope`, the condition, `_spawned` / `_file_output`: the steps a fire takes,
    minus the adding and the writing. A row the condition rejects is still rendered, flagged
    matched=False (a fire skips it - whatever its render says). `database` = what the rule sees at its
    hook (`cascade` - the earlier rules' spawns included); `layer` = `db_layer(database)` when the
    caller keeps it. An out-of-range index is clamped (a row spinner)."""
    if hooks is not None:
        declared = [h.strip().lower() for h in hooks]
        if rule.fire_when not in declared:
            return Preview(matched=None, problem=("rx_unfired_hook", _unfired(rule.fire_when, declared)))
    state = {"matched": None}
    try:
        return _preview(rule, row_index, templates, params, database, files_root, layer, state)
    except Exception as error:   # the fire's per-rule backstop, mirrored: a finding, never a crash
        return Preview(matched=state["matched"], problem=("rx_rule_crashed", f"{type(error).__name__}: {error}"))


def _preview(rule, row_index, templates, params, database, files_root, layer, state) -> Preview:
    reason = _template_problem(rule, templates)
    if reason:
        return Preview(matched=None, problem=("rx_bad_template", reason))
    db_tables = db_layer(database) if layer is None else layer
    row = {}
    if rule.source_table:
        if database is None or rule.source_table not in database:
            return Preview(matched=None, problem=("rx_unknown_table", _unknown_table("source", rule.source_table)))
        rows = db_tables[rule.source_table]                  # == _complete_rows(the source table)
        if not rows:
            if rule.action == "add_rows" and rule.target not in database:   # the fire's _spawn_rows says so,
                return Preview(matched=None,                                  # rows or none (round 6)
                               problem=("rx_unknown_table", _unknown_table("target", rule.target)))
            return Preview(matched=None, note=f"{rule.source_table} has no rows - a fire matches nothing")
        row = rows[max(0, min(row_index, len(rows) - 1))]
    scope = _scope(row, rule, params, db_tables)
    try:
        matched = expr.test(rule.condition, scope) if rule.condition else True
    except ExprError as error:
        return Preview(matched=None, problem=("rx_bad_condition", str(error)))
    state["matched"] = matched
    if rule.action == "add_rows":
        if database is None or rule.target not in database:
            return Preview(matched, problem=("rx_unknown_table", _unknown_table("target", rule.target)))
        table, spawned = database[rule.target], []
        try:
            for values in _spawned(rule, templates, scope, row):
                spawned.append(table.stamped(values))       # as add_row stores it (the uid included)
        except ExprError as error:
            return Preview(matched, rows=spawned, problem=("rx_bad_template", _bad_rows(rule, error)))
        return Preview(matched, rows=spawned)
    path, text, problem = _file_output(rule, templates, scope,
                                       config.output_root() if files_root is None else files_root)
    return Preview(matched, path=path or "", text=text or "", problem=problem)


def _copy(table: Table) -> Table:
    """A table the cascade may spawn into without touching the original (rows shared, list copied)."""
    copy = Table(table.name, columns=table.columns, json_columns=table.json_columns, key_columns=table.key_columns)
    copy.rows = list(table.rows)
    return copy


def copy_database(database):
    """A Database the builder may settle / spawn into without touching the original (rows shared, each
    table's row list copied)."""
    return Database([_copy(database[name]) for name in database.names()])


def cascade(rules, rule: Rule, database, *, templates: dict, params: dict) -> tuple:
    """The Database `rule` sees WITHIN its hook's fire: `database` plus the rows every EARLIER add_rows
    rule of that hook spawns (CSV order - the chain reaction within one hook), each through the
    fire's own `_act` on a COPY (nothing saved; a file rule changes no table and is skipped). Returns
    (that database, the earlier rules' problems); no earlier spawner = `database` itself."""
    earlier = []
    for other in rules:
        if other is rule:
            break
        if other.fire_when == rule.fire_when and other.action == "add_rows":
            earlier.append(other)
    if database is None or not earlier:
        return database, []
    copy = Database([_copy(database[name]) for name in database.names()])
    db_tables, problems = _db_tables(copy), []
    for other in earlier:
        tally = {"created": 0}
        _matched, found = _act(other, copy, templates, params, db_tables, "", tally)
        problems.extend(found)
        if tally["created"]:
            db_tables = _db_tables(copy)                      # as the fire rebuilds `_db` after a spawn
    return copy, problems


def has_business(hook: str, rows, hooks=None) -> bool:
    """Whether `fire(hook, ...)` would act for this rule index (`rows` = the reactions.csv rows): a rule
    on the hook, or a rule-INDEX problem (every hook's business) - False = the strict no-op. The
    builder models the run-plan with it: a database-less hook WITH business is settled into the
    next database, its record attached (`settle_view`)."""
    compiled, tagged = _compile(rows)
    hook = hook.strip().lower()
    if hooks is not None:
        declared = [h.strip().lower() for h in hooks]
        tagged = [(owner if owner in declared else None, finding) for owner, finding in tagged]
        if any(r.fire_when not in declared for r in compiled):
            return True                                       # rx_unfired_hook: every hook's business
        compiled = [r for r in compiled if r.fire_when in declared]
    return any(r.fire_when == hook for r in compiled) or any(owner in (hook, None) for owner, _f in tagged)


def settle_view(database, deferred=None) -> list:
    """What a `settle` makes of `deferred` - WITHOUT saving: the reaction-record tables attached from the
    on-disk record (both or neither), the hook's audit rows REPLACED by the deferred ones, its findings
    recorded into validation_issues - exactly `_persist`, minus the write. No `deferred`: the record
    attached only. Returns the problems as text (a record that will not load)."""
    if deferred is None:
        try:
            _attach_record(database, config.database_dir())
        except Exception as error:  # noqa: BLE001 - the fire reports rx_record_unreadable; the builder notes it
            return [f"the reaction record does not load: {error}"]
        return []
    problems = _persist(database, deferred.hook, deferred.log_rows, deferred.findings, save=False)
    return [f"{p.type}: {p.detail}" for p in problems]


def lint(templates: dict, rule: Rule | None = None, database=None, hooks=None) -> list:
    """What a fire would report for `templates`, found WITHOUT firing -> [tempemplator.Problem]. Every
    entry is judged for its KIND: a TEXT template (a string) by `tempemplator.lint` (every branch), a
    ROW template by `_row_template_problem` + each value by `tempemplator.lint_line` (`where` =
    (entry number, field)); anything else is neither. With a `rule` - its hook's `database` (None = a
    database-less hook) and the run-plan's `hooks` - the rule's own template is also judged in the
    rule's E1 scope (the matched row's columns + _params/_rule/_db; the hook's tables for the loops),
    and the RULE's own problems come back with template=None: a template of the wrong kind, a table
    absent at the hook, a hook never fired, a target that will not render."""
    problems, fields, tables, json, json_fields = [], None, None, None, None
    values = None
    if rule is not None:
        fields, tables, json, json_fields = _lint_rule(rule, templates, database, hooks, problems)
        values = _column_values(rule, database)
    text_start = rule.template if rule is not None and rule.action == "file" else None
    problems.extend(tempemplator.lint(templates, start=text_start, fields=fields, tables=tables,
                                      json=json, json_fields=json_fields, values=values))
    row_start = rule.template if rule is not None and rule.action == "add_rows" else None
    for name, body in templates.items():
        if isinstance(body, str):
            continue
        if not isinstance(body, list):
            problems.append(tempemplator.Problem(name, None, 0, 0, f"template {name!r} is neither a TEXT "
                                                 "template (a string) nor a ROW template (a list of "
                                                 "{field: template} maps)", "error"))
            continue
        shape = _row_template_problem(name, body)
        if shape:
            problems.append(tempemplator.Problem(name, None, 0, 0, shape, "error"))
        own = name == row_start
        for number, spec in enumerate(body, start=1):
            for column, value in (spec.items() if isinstance(spec, dict) else ()):
                if isinstance(value, str):
                    found = tempemplator.lint_line(value, fields=fields if own else None, tables=tables if own else None,
                                                   json=json_fields if own else None,
                                                   values=(lambda path: values(None, path) if "." not in path else ())
                                                   if own and values is not None else None)
                    problems.extend(tempemplator.Problem(name, (number, str(column)), s, e, message, severity)
                                    for s, e, message, severity in found)
    return problems


def _lint_rule(rule: Rule, templates: dict, database, hooks, problems: list) -> tuple:
    """The rule's own problems (appended, template=None) -> its E1 (fields, tables, {table: JSON columns},
    the source row's JSON fields); fields None when the source table is absent (every hole would read
    as missing - one problem says why)."""
    def problem(message, where=None, start=0, end=0, severity="error"):
        problems.append(tempemplator.Problem(None, where, start, end, f"rule {rule.name!r}: {message}", severity))

    reason = _template_problem(rule, templates)
    if reason:
        problem(reason)
    declared = [h.strip().lower() for h in hooks] if hooks is not None else None
    if declared is not None and rule.fire_when not in declared:
        problem(f"hook {rule.fire_when!r} is never fired by this run-plan (it fires: {', '.join(declared)})")
    tables = {} if database is None else {name: database[name].effective_columns() for name in database.names()}
    json = {} if database is None else {name: _json_valued(database[name]) for name in database.names()}
    json_fields = json.get(rule.source_table, frozenset())
    fields = {"_params", "_rule", "_db"}
    if rule.source_table:
        if rule.source_table in tables:
            fields |= set(tables[rule.source_table])
        else:
            problem(_unknown_table("source", rule.source_table))
            fields = None
    if rule.action == "add_rows" and rule.target not in tables:
        problem(_unknown_table("target", rule.target))
    if rule.action == "file":
        for start, end, message, severity in tempemplator.lint_line(rule.target, fields=fields, tables=tables,
                                                                    json=json_fields, stored=False):
            problem(f"target {rule.target!r}: {message}", "target", start, end, severity)
        refusal = _literal_refusal(rule.target)
        if refusal is not None:
            start, end, why = refusal
            problem(f"target {rule.target!r}: {why} - the fire refuses every row (rx_file_write)", "target",
                    start, end)
    return fields, tables, json, json_fields


def _column_values(rule: Rule, database):
    """`(table - None for the rule's own source table, column) -> the distinct non-blank values its rows hold there`
    (a list / object left to the JSON warning) - a hole's format spec is tried on them (C-025 refute round 6: a
    `{$qty:,}` over a text column linted clean while the fire fails on every row holding text). Each column is
    read once per lint, only when a hole asks."""
    cache = {}

    def values(table, column):
        name = rule.source_table if table is None else table
        if (name, column) not in cache:
            found = {}
            if database is not None and name and name in database:
                for row in database[name].rows:
                    value = row.get(column)
                    if value is None or value == "" or isinstance(value, (list, dict)):
                        continue
                    found.setdefault((type(value), value), value)
            cache[(name, column)] = tuple(found.values())
        return cache[(name, column)]
    return values


def _json_valued(table) -> frozenset:
    """`table`'s declared JSON columns that HOLD a list / object in its rows - a format spec fails on those
    rows. A declared JSON column holding text (a staged I/O-List cell) renders as the text it is."""
    return frozenset(column for column in table.json_columns
                     if any(isinstance(row.get(column), (list, dict)) for row in table.rows))


def _literal_refusal(target: str):
    """(start, end, why) of LITERAL target text the fire refuses whatever the row renders - None when there is
    none. A hole is data: it may render any text (a separator, a drive, a device prefix - `{$p}//?/C:`), so a
    literal is refused only where NO rendering of the holes lets the fire take it (the fire's own guards,
    `_file_output` / `_path_refusal`, read on the literal text):
    - a character a Windows path refuses (`<>"|*`, a control character) - and a '?' unless it may be a device
      prefix's (what precedes it may render two separators, and a separator or a hole follows);
    - a ':' unless it may be a DRIVE's: what precedes it may render exactly ONE ASCII letter, or a device prefix
      and one (`C:`, `{$d}:`, `{$p}C:`, `\\\\./C:` - C-024 refute round 19's note), and a separator or a hole
      follows;
    - on Windows the path shapes - see `_literal_path_refusal`."""
    atoms = _target_atoms(target)
    for index, (ch, start, end) in enumerate(atoms):
        if ch is None:
            continue
        if _WINDOWS and ch != "?" and (ch in _INVALID_PATH or ord(ch) < 32):
            return start, end, f"{ch!r} is not allowed in a Windows path"
        if _WINDOWS and ch == "?" and not _may_mark_device(atoms, index):
            return start, end, "'?' is not allowed in a Windows path"
        if ch == ":" and not _may_be_drive(atoms, index):
            return start, end, "a ':' in a relative target or a file name (a drive letter, or a hidden NTFS stream)"
    return _literal_path_refusal(atoms) if _WINDOWS else None


def _target_atoms(target: str) -> list:
    """`target` as the fire renders it: (character, start, end) per LITERAL character - `{{` renders one brace -
    and (None, start, end) per hole, which renders any text (a lone brace fails the render: lint_line says so)."""
    atoms = []
    for kind, start, end in tempemplator.brace_runs(target):
        if kind == "text":
            atoms.extend((target[i], i, i + 1) for i in range(start, end))
        elif kind == "brace":
            atoms.append((target[start], start, end))
        else:
            atoms.append((None, start, end))
    return atoms


def _may_render(atoms: list, candidates) -> bool:
    """Whether `atoms` may render exactly one of `candidates` - each literal as itself, each hole as any text."""
    pattern = re.compile("".join(".*" if ch is None else re.escape(ch) for ch, _s, _e in atoms), re.DOTALL)
    return any(pattern.fullmatch(candidate) for candidate in candidates)


def _goes_on(atoms: list, index: int) -> bool:
    """Whether a separator follows atom `index` - a literal one, or a hole that may render one."""
    return index + 1 < len(atoms) and (atoms[index + 1][0] is None or atoms[index + 1][0] in _SEPARATORS)


def _may_mark_device(atoms: list, index: int) -> bool:
    """Whether the '?' at `index` may be a device prefix's (`\\\\?\\`, `//?/`, `{$p}\\\\?\\`): what precedes it
    may render exactly two separators, and a separator (or a hole) follows."""
    return _goes_on(atoms, index) and _may_render(atoms[:index], _TWO_SEPARATORS)


def _may_be_drive(atoms: list, index: int) -> bool:
    """Whether the ':' at `index` may be a DRIVE's: what precedes it may render exactly ONE ASCII letter, or a
    device prefix and one (`C`, `{$d}`, `{$p}C`, `\\\\./C`), and a separator (or a hole) follows."""
    if not _goes_on(atoms, index):
        return False
    letters = {"C"} | {ch for ch, _s, _e in atoms[:index] if ch and ch.isascii() and ch.isalpha()}
    return _may_render(atoms[:index], [prefix + letter for letter in letters for prefix in ("",) + _DEVICE_PREFIXES])


def _literal_path_refusal(atoms: list):
    """The Windows path shapes of `_literal_refusal` - (start, end, why) or None, judged on literal text only:
    - a path rooted without a drive: a literal separator, then a literal name (`/rx/a.txt`);
    - a LITERAL `\\\\?\\` path's '/' - or its '.', '..' or empty name; a literal device path naming no drive,
      share or volume (`\\\\.\\pipe\\x`), naming only one, or climbing above it (`\\\\.\\C:\\..\\x`). A literal
      prefix is one at the start - or past leading holes when its mark is '?' (`{$p}\\\\?\\`): the fire takes
      that '?' only when the holes render nothing, so the path is that device path whenever it is written;
    - a target ending in a separator, or in a name ending in '.' / ' ' (whatever the holes before it render:
      `X.`, or a folder step - `.` / `..` name no file);
    - a name ending in a literal ' ', or in a literal '.' past its last hole but a lone `.` / `..` there (the hole
      may render a separator - a folder step); on a literal `\\\\?\\` path any name ending in '.' or ' ';
    - a device name: a literal name (`NUL`, `CON.txt`) or one opening with a literal device stem and '.'
      (`nul.{$ext}`)."""
    if atoms and atoms[0][0] in _SEPARATORS and (len(atoms) == 1 or atoms[1][0] not in (None,) + _SEPARATORS):
        return atoms[0][1], atoms[0][2], "a path rooted without a drive lands at the root of the output root's drive"
    lead = next((i for i, (ch, _s, _e) in enumerate(atoms) if ch is not None), len(atoms))   # leading holes
    mark = atoms[lead:lead + 4]
    head = "".join(ch for ch, _s, _e in mark) if len(mark) == 4 and all(ch is not None for ch, _s, _e in mark) else ""
    prefix = _device_prefix(head) if lead == 0 or head[2:3] == "?" else 0
    strict = bool(prefix) and head == _STRICT
    body = atoms[lead + prefix:] if prefix else atoms
    if strict:
        slash = next((atom for atom in body if atom[0] == "/"), None)
        if slash is not None:
            return slash[1], slash[2], f"'/' is not a separator in a {_STRICT} path (Windows takes it as written)"
    names, separators = [[]], []
    for atom in body:
        if atom[0] is not None and atom[0] in _SEPARATORS:
            names.append([])
            separators.append(atom)
        else:
            names[-1].append(atom)

    def span(number):                                  # a name's columns - an empty one: the separator after it
        name = names[number]                           # (before it, at the end; the prefix, for none)
        if name:
            return name[0][1], name[-1][2]
        near = (separators[number:number + 1] or separators[-1:] or atoms[-1:])[0]
        return near[1], near[2]

    literal = [None if any(ch is None for ch, _s, _e in name) else "".join(ch for ch, _s, _e in name)
               for name in names]
    unc = not prefix and literal[:2] == ["", ""] and len(names) > 2       # a literal \\server\share\... start
    if (prefix and literal[0] is not None) or unc:
        volume = _volume_depth(literal[0]) if prefix else 2
        if volume is None:
            return (*span(0), f"a device path's first name is its drive, share or volume - {literal[0]!r} is none "
                              "of them")
        walked = literal[2:] if unc else literal
        known = list(itertools.takewhile(lambda text: text is not None, walked))   # up to the first hole
        depth, climb = _depth(known, volume, device=bool(prefix))
        if climb is not None and not strict:                # (a `\\?\` path's '..': its own name rule says so)
            return (*span(climb + (2 if unc else 0)), "'..' climbs above the device path's drive or share (Windows "
                                                     "drops it)")
        if len(known) == len(walked) and depth <= volume:   # every name literal
            return (*span(len(names) - 1), f"the target names a {'server or a share' if unc else 'drive or a share'}, "
                                           "not a file")
    last = len(names) - 1
    for number, name in enumerate(names):
        text = literal[number]
        cut = max((i for i, (ch, _s, _e) in enumerate(name) if ch is None), default=-1)
        tail = "".join(ch for ch, _s, _e in name[cut + 1:])          # the literal text past the name's last hole
        if number == last and (not name or tail[-1:] in (".", " ") or text in (".", "..")):
            return (*span(number), "the target names no file (it ends in a separator, or in a name ending in "
                                   "'.' / ' ' - Windows drops them)")
        if text is not None and text in ("", ".", ".."):
            if strict:
                return (*span(number), f"a {_STRICT} path resolves no '.' / '..' and takes no empty name")
            continue
        if tail[-1:] == " " or (tail[-1:] == "." and (strict or text is not None or tail not in (".", ".."))):
            return (*span(number), f"a name ending in {tail[-1]!r} - Windows drops it (another file would be written)")
        first = next((i for i, (ch, _s, _e) in enumerate(name) if ch is None), len(name))
        opening = "".join(ch for ch, _s, _e in name[:first])        # the literal text before the name's first hole
        if text is not None or "." in opening:
            stem = (text if text is not None else opening).split(".")[0].rstrip(" ")
            if stem.upper() in _DEVICE_NAMES:
                return (*span(number), f"{stem!r} is a Windows device name - the text would go to the device")
    return None
