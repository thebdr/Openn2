"""The PL4 log / finding SEVERITY taxonomy - the single source of the level set.

Ordered most -> least severe:
  FAIL  - a blocking failure: HALTS the phase (+ anything depending on it); output not written/usable.
          (config-structure error, an unresolvable REQUIRED input, a missing DTD model, a locked output.)
  ERROR - a LOCALIZED failure: the offending item is skipped, the phase finishes + writes the rest
          (output usable-but-incomplete).
  WARN  - output produced, but a condition to review (a fallback used, a duplicate dropped, stale config).
  INFO  - progress / status; no action.
  SKIP  - a deliberate, documented non-action (a rule-excluded row, an N/A check, an acknowledged finding).
  PASS  - explicit success (a validation passed).
  DEBUG - developer-only diagnostics; hidden from the operator by default.

A level is identified by its FIRST CHARACTER (all distinct: F E W I S P D), so a config list may use
single chars (`[F, E, W, S, P, D]`) OR full names (`[FAIL, WARN, ...]`) interchangeably. `PHASE` is a
SECTION BANNER, not a finding level - it is always shown and never a treatment target. The treatment
registry (error_management.csv) can later RECLASSIFY a finding's effective severity per uid (incl.
escalating to FAIL) - that builds on this taxonomy.
"""
from __future__ import annotations

LEVELS = ("FAIL", "ERROR", "WARN", "INFO", "SKIP", "PASS", "DEBUG")
HALTING = frozenset({"FAIL"})          # an effective-severity in here halts the pipeline
BANNER = "PHASE"                        # a section header, not a finding (always shown)
DEFAULT_HIDDEN = frozenset({"DEBUG"})  # hidden unless explicitly listed

_BY_FIRST = {level[0]: level for level in LEVELS}   # F->FAIL, E->ERROR, W->WARN, I->INFO, S->SKIP, P->PASS, D->DEBUG


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
