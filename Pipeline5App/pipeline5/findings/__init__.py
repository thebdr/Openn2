"""Findings - how the pipeline reports, judges, and remembers everything it noticed.

One outcome system for all phases: a frozen Finding with a stable uid, a severity taxonomy, a
per-uid treatment registry (the operator has the last word), the gate that halts on FAIL, and the
renderers that turn findings into the reports you read.

WHERE TO LOOK:
  finding.py          the frozen Finding value object + recording into validation_issues
  severity.py         FAIL/ERROR/WARN/INFO/SKIP/PASS/DEBUG - first-char addressable
  treatments.py       the per-uid downgrade/escalate registry (error_management.csv)
  gate.py             gate (apply + render + HALT on FAIL) / render / has_blocking
  factory.py          the entry() Finding factory + fuzzy helpers every chapter's checks use
  messages.py         the bilingual (EN/IT) finding-text catalog
  report_model.py     InfoBlock + Cmp - the rich-report value objects
  report_renderer.py  findings -> the aligned txt + HTML reports
"""
