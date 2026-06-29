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

from pipeline4.core import config, expr
from pipeline4.domain.signals import signals_table

INPUT_REQUIRED = "<input required>"

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
