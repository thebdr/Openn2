"""The phase-100 finding messages - the English `v_*` templates ported VERBATIM from PL3's `core/i18n.py`
(PL4 has no i18n layer; the user's decision is EN-only with the SAME text, so a finding's
`(phase, type, detail)` matches PL3's for the parity oracle). `msg(slug, **fmt)` formats one template.

Slugs for 110 (I/O List) + 120 (C&E) land here with 100b; 130/140 (cross-checks) are appended with 100c.
"""
from __future__ import annotations

MESSAGES = {
    # --- 110 Validate I/O List ---
    "iolist_missing": "I/O List not found: {path}",
    "iolist_locked": "The I/O List may already be in use (open in Excel?) - close it and retry.",
    "iolist_open_error": "Could not open the I/O List: {error}",
    "no_sheet": "No I/O sheet matched {pattern}",
    "proc_sheet": "Processing sheet '{sheet}'",
    "skip_sheet": "Skipped sheet '{sheet}'",
    "col_wrong": "Wrong column name '{actual}'. Correct name for column {n} is '{expected}'",
    "col_unexpected": "Unexpected column name in column {n}: '{name}'",
    "col_duplicated": "Duplicated column name in column {n}: '{name}'",
    "ip_error": "Error in the Profinet IP cell",
    "ip_duplicated": "Duplicated IP {ip} (first seen at {first})",
    "dup_fld": "Duplicated Functional unit + Location + Device (first seen at {first})",
    "fg_exclusion": "Column G has a value, so column F must be empty",
    "addr_format": "Invalid address format",
    "pp_empty": "Empty permanent part",
    "pp_unknown": "Unknown permanent part '{value}'",
    "ts_missing": "T.S. ref is missing",
    "ip_missing": "IP address is missing",
    "pname_wrong": "Invalid Profinet name (must start with 'n' and contain none of _ . / = *)",
    "nodes_over_64": "More than 64 nodes ({n}): this card cannot drive induction-line PH SYNCH / PH FEEDBACK",
    "too_many_nodes": "Too many nodes: {n} (max 126)",
    "struck_row": "Row is struck through (excluded by policy)",
    "iolist_summary": "{sheets} sheet(s) processed, {nodes} node(s)",
    "row_ok": "All checks passed",
    # --- 120 Validate C&E Matrix ---
    "ce_absent": "Cause&Effect matrix not configured/found - C&E checks skipped",
    "ce_locked": "The Cause&Effect matrix may already be in use (open in Excel?) - close it and retry.",
    "ce_sheet_missing": "C&E matrix sheet not found: {sheet}",
    "matrix_addr_kind": "Output/internal address {addr} on the CAUSE&EFFECT MATRIX (inputs only)",
    "area_addr_kind": "Input address {addr} on an AREA sheet (outputs only)",
    "dup_addr": "Duplicated address {addr} within the sheet (first seen at {first})",
    "ce_summary": "{refs} address reference(s) checked across {sheets} sheet(s)",
}


def msg(slug: str, **fmt) -> str:
    """The English message for `slug`, formatted with **fmt. Missing slug -> the slug itself (loud)."""
    template = MESSAGES.get(slug)
    if template is None:
        return f"<{slug}>"
    return template.format(**fmt)
