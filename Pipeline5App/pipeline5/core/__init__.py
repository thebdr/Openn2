"""The kernel spine - system-blind primitives every phase builds on.

WHERE TO LOOK:
  ssot_table.py          the CSV-with-JSON-cells Table (deterministic codec, content-hash uid)
  ssot_database.py       named tables + save/load - THE single source of truth
  content_hash.py        uid(*parts) - the universal sha1 content key
  finding.py             the frozen Finding value object + recording into validation_issues
  severity.py            the FAIL/ERROR/WARN/INFO/SKIP/PASS/DEBUG taxonomy
  finding_treatments.py  the per-uid downgrade/escalate registry (error_management.csv)
  phase_gate.py          gate (apply + render + HALT on FAIL) / render / has_blocking
  report_model.py        InfoBlock + Cmp - the rich-report value objects
  i18n.py                tr(key, lang) - EN/IT
  config/                paths + params + config-CSV loaders (see its own signpost)
  expr/                  the unified $-expression engine (parser, render, runtime, scope, tools)
"""
