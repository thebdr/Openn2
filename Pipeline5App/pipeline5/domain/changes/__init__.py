"""ph100 before/after document-quality report (PL4-native, NOT part of the pipeline).

Compares a PRIOR document revision against the CURRENT one (the configured `*_previous_path` vs the
working `*_path`) and classifies every row intact / corrected / upgrade / removed to expose HUMAN
document-quality problems - a "what went wrong" analysis. It NEVER touches the SSOT or the BuilderData;
it only reads two workbook revisions and writes a graphical HTML report (+ a CSV audit trail) under
ProjectDocumentation/Reports.

The design is evidence-derived (see CHANGES_SPEC.md): row matching is node-scoped and ADDRESS-BLIND
(addresses/slots/pins are exactly what gets re-schemed, so they are never identity keys); a wholesale
re-scheme is reported as ONE event, not hundreds of defects; corrections are tiered (change_weights.csv)
and direction-tagged (gap-fill / value-change / value-loss).
"""
