"""ph200 sub-phase 210 - Script-type classification, CSV-rule-driven, over a STAGED signals row.

The rules live in `config_project/input_docs/gate_rules.csv` (In/Out/Node) + `script_type_rules.csv`
(the type ladder); both are evaluated by the UNIFIED expression engine `core.expr` (M-E2). Adding a type
is a config edit, not code. `classify(row, ...)` returns the canonical script_type (`<input required>`
when a described row matches nothing; `""` when it isn't classifiable at all) - 1:1 with PL3's
`suggested_type`.

The `row` is a STAGED signals dict (the canonical signals columns are present). The `$`-namespace IS the
signals columns: a rule references `$desc_l1`/`$desc_l1b`/`$bit`/`$id_node`/`$type_hw`/... directly and
cleans/joins them itself via `clean()`/`join()`. The `gate` is a CODE-level filter on each type rule's
`gate` column (In/Out/Node/any) - NOT a `$`-field. Matching is case-insensitive (the engine's `~`).
"""
from __future__ import annotations

import re

from pipeline4.core import config, expr
from pipeline4.domain.fillout import ranges
from pipeline4.domain.fillout.families import family_for
from pipeline4.domain.signals import signals_table

INPUT_REQUIRED = "<input required>"

# a trailing channel suffix on a script_type (an existing `n/N`, optionally wrapped `<n/N>`), to strip.
_CHAN_SUFFIX = re.compile(r"^(.*?)(\d+)/(\d+)$")

_SCOPE = None


def _scope():
    """The expr Scope for the signals namespace (the canonical signals columns), built + cached once."""
    global _SCOPE
    if _SCOPE is None:
        cols = signals_table([m["canonical"] for m in config.load_column_map("IoList")]).columns
        _SCOPE = expr.Scope(cols)
    return _SCOPE


def gate_of(row: dict, gate_rules: list) -> str:
    """First matching gate rule's `gate` (In/Out/Node), else '' (the row isn't I/O or a node)."""
    for rule in gate_rules:
        if expr.test(rule.get("when", ""), row, _scope()):
            return (rule.get("gate") or "").strip()
    return ""


def classify(row: dict, gate_rules: list | None = None, type_rules: list | None = None) -> str:
    """The script_type for one staged signals row: compute the gate, then the first matching type rule
    (within that gate or `any`). Returns '' when nothing matches (1:1 with PL3's `suggested_type`)."""
    gate_rules = config.load_gate_rules() if gate_rules is None else gate_rules
    type_rules = config.load_script_type_rules() if type_rules is None else type_rules
    gate = gate_of(row, gate_rules)
    for rule in type_rules:
        if (rule.get("gate") or "").strip() not in (gate, "any"):
            continue
        if expr.test(rule.get("when", ""), row, _scope()):
            return expr.render((rule.get("type") or "").strip(), row, _scope())
    return ""


# --- channel suffix: a multi-channel family authored as INDEPENDENT component rows ----------------- #
def _fld(row: dict) -> str:
    return f"{row.get('functional_unit', '')}{row.get('location', '')}{row.get('device', '')}"


def _base_type(st: str) -> str:
    """A script_type stripped of any `<...>` marker AND any trailing `n/N` channel suffix (`<KI1/5>`/`KI1/2`
    -> `KI`) - the stable base the channel suffix is (re)appended to (idempotent / self-healing re-runs)."""
    s = (st or "").strip().strip("<>")
    m = _CHAN_SUFFIX.match(s)
    return m.group(1) if m else s


def channel_suffixes(rows: list, families: list, signal_types: dict, base_type: dict) -> tuple:
    """Derive the channel `<n>/<N>` for every INDEPENDENT family row that is a COMPONENT of a device RANGE
    authored elsewhere (`-K66701` is component 1 of the range `-K66701..2` -> the base `KI` becomes `KI1/2`).
    The range row itself keeps its base type, and a channel that comes from the DESCRIPTION (E1/2 via `CH.n`)
    is untouched (its device is not a range). PURE (no mutation): given `base_type[uid]` = each row's
    rule-computed base script_type, returns `(suffixed, invalid)` where:
      * `suffixed` = `{uid -> marked_full_type}` for the component rows - `KI1/2` (known to signal_types) or
        the MARKED `<KI1/5>` (unknown - the operator must add the type / fix the range);
      * `invalid` = the list of `(row, derived_type)` whose derived type is unknown.
    The caller applies these per Mode-1/2 (so a human AB is still preserved) and lists the unknown in _UnresolvedIndex."""
    valid = {str(k).upper() for k in (signal_types or {})}
    # the channel map is DEFINED by the range rows that belong to a family (keyed by component FLD -> (n, N))
    range_flds = [_fld(r) for r in rows
                  if family_for(base_type.get(r.get("uid"), ""), families) is not None
                  and ranges.is_range(r.get("device") or "")]
    chan = ranges.build_channel_map(range_flds)
    suffixed, invalid = {}, []
    for r in rows:
        base = base_type.get(r.get("uid"), "")
        if not base or family_for(base, families) is None or ranges.is_range(r.get("device") or ""):
            continue
        nn = chan.get(_fld(r))
        if not nn:
            continue
        n, total = nn
        cand = f"{base}{n}/{total}"
        if cand.upper() in valid:
            suffixed[r["uid"]] = cand
        else:
            suffixed[r["uid"]] = f"<{cand}>"
            invalid.append((r, cand))
    return suffixed, invalid


def unmark(script_type) -> str:
    """A script_type stripped of the `<...>` unknown-type marker (`<KI1/5>` -> `KI1/5`)."""
    s = (script_type or "").strip()
    return s[1:-1] if s.startswith("<") and s.endswith(">") else s
