"""Phase 100 - Documents Validation. The hand-authored I/O List + Cause&Effect validators.

Clean-room port of PL3's `domain/validation/`, emitting PL4 `core.finding.Finding` (carrying the rich
`info`/`cmp`/`location2` render payload) instead of PL3's `LogEntry`, and reusing the already-built
severity/treatment spine (`core.finding`/`treatments`/`run`). The five sub-phases: 110 standalone I/O List,
120 standalone C&E, 130 cross-check CEM->IOL, 140 cross-check IOL->CEM, 150 diagnosis-slot uniqueness
(150 deferred). 110/120 read the RAW workbooks (facts staging normalizes away); 130/140/150 read the SSOT.
"""
