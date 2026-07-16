"""Phase 600 (Diagnosis) SSOT table definitions - the table DEFS only (like `db_members.py` for 520).

- `diagnosis_cabinets` - the parent: one row per diagnosis cabinet (the DiagnosisBlocks sheet, read at
  staging). `template_type` drives the SCL's 01-04 cabinet variant; `swp` is the ID_SWP.
- `diagnosis_entries` - the UNIFIED child: one row per diagnosis element, `source` = "io" (an in-diag
  signal) | "logic" (a diagnosis_logic_rule firing on a row). Both DiagList_IO.csv and DiagList_Logic.csv
  are projections of this one table (filter by `source`); the OPC SCL reads the channel columns
  (cabinet/bit/is_warning/in_binding/ml_value/fl_value). `diag_columns` is the frozen {header->cell}
  snapshot the DiagList projector picks (so a config column change can't drift the stored rows).
"""
from __future__ import annotations

from pipeline5.truth.table import Table


def diagnosis_cabinets_table() -> Table:
    """One row per diagnosis cabinet (ported from PL3 `load_diagnostic_blocks`: ID_Local -> attrs)."""
    return Table(
        "diagnosis_cabinets",
        columns=["uid", "cabinet_id", "index", "fld", "template_type", "swp"],
        json_columns=[],
        key_columns=["cabinet_id"],
    )


def diagnosis_entries_table() -> Table:
    """One row per diagnosis element (the unified DiagList_IO + DiagList_Logic parent)."""
    return Table(
        "diagnosis_entries",
        columns=["uid", "source", "source_signal", "rule_name", "cabinet", "bit", "is_warning",
                 "in_binding", "ml_value", "fl_value", "diag_columns"],
        json_columns=["is_warning", "diag_columns"],
        key_columns=["source", "source_signal", "rule_name", "cabinet", "bit", "is_warning"],
    )
