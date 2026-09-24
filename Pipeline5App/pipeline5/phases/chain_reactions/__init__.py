"""Chapter: CHAIN REACTIONS - the app's conditional-data-creation spine (one of its key powers).

One signal from the I/O List may spawn many more facts: extra SSOT rows, diagnosis data, interface
sheets, whole generated-code files. Instead of hand-coding each such cascade, a REACTION RULE
declares it in config: WHEN to fire (before/after a phase), WHICH rows trigger it (an expr
condition over a source table), and WHAT to do (spawn expr-filled rows into an SSOT table, or
render a Tempemplator text template and APPEND it to a file). Every firing is audited in the
`chain_reactions_log` SSOT table; every spawned row carries `spawned_by` + `source_uid` provenance.

  engine.py    the rule engine: compile the config rules, match, spawn/append, log, `fire(hook)`

Config (per-system tier, 4-tier resolved): `chain_reactions/reactions.csv` (the terse rule index)
+ `chain_reactions/templates.yaml` (the reusable named templates - row AND text kinds). The text
renderer itself is src://pipeline5/language/tempemplator.py (values = expr, structure = @directives).
Hooks are fired by the SYSTEM RUN-PLAN (e.g. src://pipeline5/systems/plc_based/siemens_s7/safety/main.py
around its staging leg) - phase buttons and Run-all fire identically because the hook lives in the
handler, not the GUI.
"""
