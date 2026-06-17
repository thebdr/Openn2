"""Validation: cross-check the C&E matrix and AREA sheets against the I/O List, and
sanity-check the diagnosis bit map of the in-diagnosis signals.

Match key = FUNCTIONAL UNIT + LOCATION + DEVICE; address = the Bit/address cell.
  I/O List : functional_unit (O) + location (P) + device (Q), address = bit (G)
  C&E      : J + K + L,                              address = F
  AREA n   : column A (already concatenated),        address = column C
Every C&E / AREA reference must exist in the I/O List with a matching address.
Only the CAUSE&EFFECT MATRIX and AREA n sheets are checked - all other sheets
are ignored.

Diagnosis bit map (I/O List, columns Diag Cabinet AE / Diag Bit AF): every signal
flagged in-diagnosis must carry a numeric Diag Cabinet + Diag Bit (else it cannot be
placed in the OPC diagnosis DWords), and no two may share the same cabinet/bit within
the same alarm/warning family (they would overwrite one another in the packed DWord).

Reverse C&E (I/O List -> C&E): every I/O signal that *should* be in the C&E must appear
there, matched by BOTH its device key (FLD) and its address. A typed row uses its signal
type's `ce_mandatory` (yes -> ERROR if not fully present, warn -> WARNING, no -> ignored);
an untyped/unknown row is checked when it carries a device designation (FLD = FU+LOC+DEV) -
or, device-less, a non-empty desc_l1/desc_l1b - plus an address, an absent one being an
ERROR when its description names a safety concept (the params.yaml `ce_mandatory_words`,
default emergency/safety/relay/contactor/enable) else a WARNING. A partial match - only the
FLD or only the address differs - is logged at the same severity, printing both sides.
Fuzzy word matching uses params.yaml `ce_fuzzy_chars` (Levenshtein tolerance; 0 disables).
Untyped rows whose description matches `ce_excluded_words` (params.yaml) are skipped - but a
`ce_mandatory_words` match wins, and typed rows are never excluded (signal-type rules
prevail); `ce_full_check` (params.yaml, default false) ignores that list. `ce_always_excluded_words`
(substring only, NO fuzzy) ALWAYS skips a row (typed or untyped), overriding everything
(e.g. 'ch2' to drop channel-2 rows). Every PASS/SKIP is logged; `ce_full_print` (params.yaml)
controls whether the live display (GUI/console) shows the passing/skipped rows (greyed) - the
`documents_validation_report.txt` and the colour-coded `documents_validation_report.html` (a dark page mirroring the log
viewer, renders in any browser) always hold the full record.

The log runs the requested phases of a stable 5-phase interface (`validate(phases=…)`):
  0A. I/O List standalone      - format/content checks (the VBA port, `iolist_checks`);
  0B. C&E Matrix standalone    - placeholder (no checks yet);
  1.  C&E in IOList            - the forward check (check_ce_matrix + check_area_sheets);
  2.  IOList in C&E            - the reverse check (check_ce_mandatory);
  3.  Diagnosis Coherence Check - the diagnosis bit map (check_diagnosis_bits).
Every check is logged (pass AND fail); each entry carries an info block
`bit | FLD | desc_l1 | desc_l1b | drawing | script_type-index` (from the I/O row, or a C&E
pseudo-row for unmatched forward references) and the offending workbook (`path`) so the GUI
can link the I/O List vs the C&E document.

This module was split into a package; the names below are re-exported so
`from pipeline2.core import validation` and every `validation.<name>` reference (incl.
underscore-prefixed ones) keep working identically.
"""
from __future__ import annotations

# --- model: leaf helpers, data classes, constants ---------------------------- #
from .model import (
    CE_MANDATORY_WORDS,
    ALL_PHASES,
    NONE_VALUE,
    DOC_IO,
    DOC_CE,
    Cmp,
    LogEntry,
    _norm,
    _key,
    _addr,
    _raw,
    _join_set,
    _row_info_parts,
    _row_info,
    _caller_info,
    _is_warning,
    _io_loc,
    _dev_label,
    _row_text,
    _levenshtein,
    _first_match,
    _matches_words,
    _banner,
)

# --- indexes ----------------------------------------------------------------- #
from .indexes import (
    build_io_index,
    build_ce_index,
)

# --- checks ------------------------------------------------------------------ #
from .checks import (
    _check_reference,
    check_ce_matrix,
    check_area_sheets,
    check_diagnosis_bits,
    _ce_match,
    check_ce_mandatory,
    validate,
)

# --- render ------------------------------------------------------------------ #
from .render import (
    RenderRec,
    _op,
    _cmp_body,
    _cell_link,
    render_lines,
    _HTML_CSS,
    _html_escape,
    _rec_text,
    _html_rec,
    write_log,
)

__all__ = [
    # model
    "CE_MANDATORY_WORDS", "ALL_PHASES", "NONE_VALUE", "DOC_IO", "DOC_CE",
    "Cmp", "LogEntry",
    "_norm", "_key", "_addr", "_raw", "_join_set",
    "_row_info_parts", "_row_info", "_caller_info",
    "_is_warning", "_io_loc", "_dev_label", "_row_text",
    "_levenshtein", "_first_match", "_matches_words", "_banner",
    # indexes
    "build_io_index", "build_ce_index",
    # checks
    "_check_reference", "check_ce_matrix", "check_area_sheets",
    "check_diagnosis_bits", "_ce_match", "check_ce_mandatory", "validate",
    # render
    "RenderRec", "_op", "_cmp_body", "_cell_link", "render_lines",
    "_HTML_CSS", "_html_escape", "_rec_text", "_html_rec", "write_log",
]
