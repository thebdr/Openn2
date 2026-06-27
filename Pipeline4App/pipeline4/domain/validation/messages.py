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
    # --- 130 cross-check CEM -> IOL ---
    "cem_ref_empty": "Reference carries no device designation",
    "cem_addr_ok": "Address found in the I/O List with a matching FLD",
    "cem_addr_fld": "Address found in the I/O List under a DIFFERENT FLD",
    "cem_addr_none": "Address not found in the I/O List",
    "cem_fld_ok": "FLD found in the I/O List at a matching address",
    "cem_fld_addr": "FLD found in the I/O List at a DIFFERENT address",
    "cem_fld_none": "FLD not found in the I/O List",
    "cem_summary": "{refs} C&E reference(s) checked against the I/O List",
    # --- 140 cross-check IOL -> CEM ---
    "iol_cem_match": "Present in the Cause&Effect matrix; device and address match.",
    "iol_cem_missing_mandatory": "Mandatory signal absent from the Cause&Effect matrix.",
    "iol_cem_missing_safety": "Safety-related signal absent from the Cause&Effect matrix.",
    "iol_cem_missing_plain": "Not found in the Cause&Effect matrix.",
    "iol_cem_fld_only": "Present in the Cause&Effect matrix at a different address.",
    "iol_cem_addr_only": "Address present in the Cause&Effect matrix under a different device.",
    "iol_cem_skipped": "Skipped - matches excluded word '{word}'.",
    "iol_cem_unclassified": "Untyped, not safety-related - not cross-checked.",
    "iol_cem_not_required": "Type not required in the Cause&Effect matrix - not cross-checked.",
    "iol_cem_summary": "{checked} I/O signal(s) checked against the Cause&Effect matrix",
    "iol_cem_skip_summary": "{skipped} signal(s) skipped by the exclusion lists",
}


def msg(slug: str, **fmt) -> str:
    """The English message for `slug`, formatted with **fmt. Missing slug -> the slug itself (loud)."""
    template = MESSAGES.get(slug)
    if template is None:
        return f"<{slug}>"
    return template.format(**fmt)
