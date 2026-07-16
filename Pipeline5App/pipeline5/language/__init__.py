"""The languages - how humans express rules, templates, and text to the pipeline.

WHERE TO LOOK:
  expr/       the $-expression engine (conditions, templates, data functions) - the ONE grammar
              every config column speaks; the fx dialog previews it live
  i18n.py     tr(key, lang) - the human-language layer (EN/IT)
  templating/ (arrives with P-009) the Tempemplator text renderer - @use/@for/@if over expr values
"""
