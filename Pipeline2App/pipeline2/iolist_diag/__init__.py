"""I/O-list diagnosis populator.

A Pipeline2 stage that runs immediately before `staging`: on a fresh Emergency I/O-list it
fills `script_type` (AB), `index` (AD), `diag_cabinet` (AE) and `diag_bit` (AF), generates the
`DiagnosisBlocks` sheet, and writes an `_UnresolvedIndex` report. Idempotent and
non-destructive (never overwrites a human-filled cell - only audits it). See populate.populate.
"""
from pipeline2.iolist_diag.populate import PopulateResult, populate

__all__ = ["populate", "PopulateResult"]
