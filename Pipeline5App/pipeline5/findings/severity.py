"""The PL4 log / finding SEVERITY taxonomy - the single source of the level set.

Every level is a FOUR-LETTER code (the user's original design: the log's `[XXXX]` column is always
exactly 4 chars wide). Ordered most -> least severe:
  FAIL - a blocking failure: HALTS the phase (+ anything depending on it); output not written/usable.
         (config-structure error, an unresolvable REQUIRED input, a missing DTD model, a locked output.)
  ERRR - a LOCALIZED failure: the offending item is skipped, the phase finishes + writes the rest
         (output usable-but-incomplete).
  WARN - output produced, but a condition to review (a fallback used, a duplicate dropped, stale config).
  INFO - progress / status; no action.
  SKIP - a deliberate, documented non-action (a rule-excluded row, an N/A check, an acknowledged finding).
  PASS - explicit success (a validation passed).
  RSLT - a phase's ENDING SUMMARY line (counts/outcome -> target) - a LOG level with its own colour
         (user spec); no FINDING ever carries it and it is never a treatment target. Shown by default;
         a normal Levels-dropdown toggle (the yaml wins - not code-forced).
  DEBG - developer-only diagnostics; hidden from the operator by default.

A level is identified by its FIRST CHARACTER (all distinct: F E W I S P R D), so a config list may use
single chars (`[F, E, W, S, P, R, D]`), the 4-letter codes, OR legacy full names (`ERROR`, `DEBUG` - old
configs/registries resolve unchanged) interchangeably. `PHASE` is a SECTION BANNER and `HEAD` the
column-header line - chrome, not finding levels; always shown, never treatment targets. The treatment
registry (error_management.csv) can later RECLASSIFY a finding's effective severity per uid (incl.
escalating to FAIL) - that builds on this taxonomy.
"""
from __future__ import annotations

LEVELS = ("FAIL", "ERRR", "WARN", "INFO", "SKIP", "PASS", "RSLT", "DEBG")
HALTING = frozenset({"FAIL"})          # an effective-severity in here halts the pipeline
# The levels the GUI can never hide (greyed + checked in the Levels dropdown; the saver always
# includes them): the failures + the progress narrative (INFO) + the phase results (RSLT).
UNHIDEABLE = frozenset({"FAIL", "ERRR", "INFO", "RSLT"})
BANNER = "PHASE"                        # a section header, not a finding (always shown)
HEADER = "HEAD"                         # the per-group column-header log line (chrome, always shown)
DEFAULT_HIDDEN = frozenset({"DEBG"})   # hidden unless explicitly listed

_BY_FIRST = {level[0]: level for level in LEVELS}   # F->FAIL, E->ERRR, W->WARN, I->INFO, S->SKIP, P->PASS, D->DEBG


def resolve(token) -> str | None:
    """A config entry ('F' / 'FAIL' / 'fail' / 'Fail…') -> the canonical level by FIRST CHAR; None if
    the first character names no level."""
    text = str(token if token is not None else "").strip().upper()
    return _BY_FIRST.get(text[:1]) if text else None


def resolve_set(tokens) -> set:
    """A list of config entries -> the set of canonical levels to SHOW. The `PHASE` banner is always
    included. Unknown entries are ignored."""
    shown = {BANNER}
    for token in tokens or ():
        level = resolve(token)
        if level:
            shown.add(level)
    return shown


def default_shown() -> set:
    """The shown set when no `log_levels` is configured: every finding level except the DEFAULT_HIDDEN
    (DEBUG) + the banner."""
    return {BANNER} | (set(LEVELS) - DEFAULT_HIDDEN)
