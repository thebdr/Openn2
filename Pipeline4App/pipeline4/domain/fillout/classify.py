"""ph200 sub-phase 210 - Script-type classification, CSV-rule-driven (replaces PL3's hard-coded §6 ladder
in `domain/iolist_diag/script_type.py`).

The rules live in `config_project/input_docs/gate_rules.csv` (In/Out/Node) + `script_type_rules.csv`
(the type ladder); both are evaluated by `core.rule_expr` (a reusable expression engine). Adding a type is
a config edit, not code. `classify(raw, ...)` returns the canonical script_type (`<input required>` when a
described row matches nothing; `""` when it isn't classifiable at all) - 1:1 with PL3's `suggested_type`.

The CONTEXT a rule sees per row: cleaned `d1`/`d2` (description col K / L) + `desc` (their join), `addr`
(bit col G), `id_node` (col F), `type_hw` (Type col R), `functional_unit`/`location`/`device`, the computed
`gate`, and `INPUT_REQUIRED` (the sentinel, for `{INPUT_REQUIRED}` results). Matching is case-insensitive;
text is CLEANED here (control chars -> space, whitespace collapsed) before the rules run.
"""
from __future__ import annotations

import re

from pipeline4.core import config, rule_expr

INPUT_REQUIRED = "<input required>"

_CTRL = re.compile(r"[\x00-\x1f]")
_WS = re.compile(r"\s+")


def clean(value) -> str:
    """PL3's `_clean`: control chars -> space, whitespace runs collapsed, stripped."""
    return _WS.sub(" ", _CTRL.sub(" ", str(value if value is not None else ""))).strip()


def build_ctx(raw: dict) -> dict:
    """The rule context for one raw IoList row (canonical fields from `column_map`)."""
    d1, d2 = clean(raw.get("desc_l1")), clean(raw.get("desc_l1b"))
    return {
        "d1": d1,
        "d2": d2,
        "desc": (d1 + " " + d2).strip(),
        "addr": str(raw.get("bit") or ""),
        "id_node": str(raw.get("id_node") or ""),
        "type_hw": str(raw.get("type_hw") or "").strip(),
        "functional_unit": str(raw.get("functional_unit") or ""),
        "location": str(raw.get("location") or ""),
        "device": str(raw.get("device") or ""),
        "INPUT_REQUIRED": INPUT_REQUIRED,
    }


def gate_of(ctx: dict, gate_rules: list) -> str:
    """First matching gate rule's `gate` (In/Out/Node), else '' (the row isn't I/O or a node)."""
    for rule in gate_rules:
        if rule_expr.test(rule.get("when", ""), ctx):
            return (rule.get("gate") or "").strip()
    return ""


def classify(raw: dict, gate_rules: list | None = None, type_rules: list | None = None) -> str:
    """The script_type for one raw row: compute the gate, then the first matching type rule (within that
    gate or `any`). Returns '' when nothing matches (1:1 with PL3's `suggested_type`)."""
    gate_rules = config.load_gate_rules() if gate_rules is None else gate_rules
    type_rules = config.load_script_type_rules() if type_rules is None else type_rules
    ctx = build_ctx(raw)
    ctx["gate"] = gate_of(ctx, gate_rules)
    for rule in type_rules:
        if (rule.get("gate") or "").strip() not in (ctx["gate"], "any"):
            continue
        if rule_expr.test(rule.get("when", ""), ctx):
            return rule_expr.render((rule.get("type") or "").strip(), ctx)
    return ""
