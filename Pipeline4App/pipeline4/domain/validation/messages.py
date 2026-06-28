"""The phase-100 finding messages - bilingual EN/IT (the EN from PL3's `core/i18n.py`, the IT from the SAME
PL3 table). `msg(slug, **fmt)` formats one template in the ACTIVE language.

COSMETIC RULE (user): always use the PLURAL form - never the singular-or-plural hedge (`(s)` in EN, `/i`
in IT). So the count-bearing summary lines read `1 sheets` / `1 fogli`, even at count 0 or 1. This is the
ONE deliberate deviation from PL3's verbatim text (the 5 INFO summary slugs); they are not recorded to
`validation_issues` nor part of any BuilderData, so it is a display-only change.

The whole reason i18n exists in this project is the **operator-facing validation log + reports**: an
Italian operator must read the findings in Italian. A finding's detail is built HERE, in the active
language, exactly like PL3 (`tr("v_<type>", ctx.lang)`) - so the rendered line + the .txt/.html reports
come out localized with NO change to the 53 builder call sites or to `io/render.py`.

The active language is AMBIENT for the duration of a validation run (PL3 carried it on `ctx.lang`; PL4 has
no ctx, so a run sets it via `active_lang(lang)` and restores it - the GUI runs one phase at a time, so the
ambient is single-threaded). Default `en` keeps the parity oracle + a headless call English. The finding
`uid` hashes the localized detail (as in PL3): treatments are keyed per operating language (an operator
works in one language).
"""
from __future__ import annotations

from contextlib import contextmanager

# slug -> {"en": template, "it": template}. Placeholders use str.format syntax ({name}). EN == the prior
# verbatim text (parity preserved); IT from PL3's `v_<slug>`.
MESSAGES = {
    # --- 110 Validate I/O List ---
    "iolist_missing": {"en": "I/O List not found: {path}", "it": "I/O List non trovata: {path}"},
    "iolist_locked": {"en": "The I/O List may already be in use (open in Excel?) - close it and retry.",
                      "it": "La I/O List potrebbe essere gia in uso (aperta in Excel?) - chiuderla e riprovare."},
    "iolist_open_error": {"en": "Could not open the I/O List: {error}",
                          "it": "Impossibile aprire la I/O List: {error}"},
    "no_sheet": {"en": "No I/O sheet matched {pattern}", "it": "Nessun foglio I/O corrisponde a {pattern}"},
    "proc_sheet": {"en": "Processing sheet '{sheet}'", "it": "Elaborazione foglio '{sheet}'"},
    "skip_sheet": {"en": "Skipped sheet '{sheet}'", "it": "Foglio ignorato '{sheet}'"},
    "col_wrong": {"en": "Wrong column name '{actual}'. Correct name for column {n} is '{expected}'",
                  "it": "Nome colonna errato '{actual}'. Il nome corretto per la colonna {n} e '{expected}'"},
    "col_unexpected": {"en": "Unexpected column name in column {n}: '{name}'",
                       "it": "Nome colonna inatteso nella colonna {n}: '{name}'"},
    "col_duplicated": {"en": "Duplicated column name in column {n}: '{name}'",
                       "it": "Nome colonna duplicato nella colonna {n}: '{name}'"},
    "ip_error": {"en": "Error in the Profinet IP cell", "it": "Errore nella cella IP Profinet"},
    "ip_duplicated": {"en": "Duplicated IP {ip} (first seen at {first})",
                      "it": "IP duplicato {ip} (prima occorrenza in {first})"},
    "dup_fld": {"en": "Duplicated Functional unit + Location + Device (first seen at {first})",
                "it": "Functional unit + Location + Device duplicati (prima occorrenza in {first})"},
    "fg_exclusion": {"en": "Column G has a value, so column F must be empty",
                     "it": "La colonna G ha un valore, quindi la colonna F deve essere vuota"},
    "addr_format": {"en": "Invalid address format", "it": "Formato indirizzo non valido"},
    "pp_empty": {"en": "Empty permanent part", "it": "Parte permanente vuota"},
    "pp_unknown": {"en": "Unknown permanent part '{value}'", "it": "Parte permanente sconosciuta '{value}'"},
    "ts_missing": {"en": "T.S. ref is missing", "it": "Riferimento T.S. mancante"},
    "ip_missing": {"en": "IP address is missing", "it": "Indirizzo IP mancante"},
    "pname_wrong": {"en": "Invalid Profinet name (must start with 'n' and contain none of _ . / = *)",
                    "it": "Nome Profinet non valido (deve iniziare con 'n' e non contenere _ . / = *)"},
    "nodes_over_64": {"en": "More than 64 nodes ({n}): this card cannot drive induction-line PH SYNCH / PH FEEDBACK",
                      "it": "Piu di 64 nodi ({n}): questa scheda non puo gestire PH SYNCH / PH FEEDBACK della linea a induzione"},
    "too_many_nodes": {"en": "Too many nodes: {n} (max 126)", "it": "Troppi nodi: {n} (max 126)"},
    "struck_row": {"en": "Row is struck through (excluded by policy)", "it": "Riga barrata (esclusa dalla policy)"},
    "iolist_summary": {"en": "{sheets} sheets processed, {nodes} nodes",
                       "it": "{sheets} fogli elaborati, {nodes} nodi"},
    "row_ok": {"en": "All checks passed", "it": "Tutti i controlli superati"},
    # --- 120 Validate C&E Matrix ---
    "ce_absent": {"en": "Cause&Effect matrix not configured/found - C&E checks skipped",
                  "it": "Matrice Cause&Effect non configurata/trovata - verifiche C&E ignorate"},
    "ce_locked": {"en": "The Cause&Effect matrix may already be in use (open in Excel?) - close it and retry.",
                  "it": "La matrice Cause&Effect potrebbe essere gia in uso (aperta in Excel?) - chiuderla e riprovare."},
    "ce_sheet_missing": {"en": "C&E matrix sheet not found: {sheet}", "it": "Foglio matrice C&E non trovato: {sheet}"},
    "matrix_addr_kind": {"en": "Output/internal address {addr} on the CAUSE&EFFECT MATRIX (inputs only)",
                         "it": "Indirizzo di uscita/interno {addr} nella CAUSE&EFFECT MATRIX (solo ingressi)"},
    "area_addr_kind": {"en": "Input address {addr} on an AREA sheet (outputs only)",
                       "it": "Indirizzo di ingresso {addr} in un foglio AREA (solo uscite)"},
    "dup_addr": {"en": "Duplicated address {addr} within the sheet (first seen at {first})",
                 "it": "Indirizzo duplicato {addr} nel foglio (prima occorrenza in {first})"},
    "ce_summary": {"en": "{refs} address references checked across {sheets} sheets",
                   "it": "{refs} riferimenti di indirizzo verificati su {sheets} fogli"},
    # --- 130 cross-check CEM -> IOL ---
    "cem_ref_empty": {"en": "Reference carries no device designation",
                      "it": "Il riferimento non riporta alcun dispositivo"},
    "cem_addr_ok": {"en": "Address found in the I/O List with a matching FLD",
                    "it": "Indirizzo trovato nella I/O List con FLD corrispondente"},
    "cem_addr_fld": {"en": "Address found in the I/O List under a DIFFERENT FLD",
                     "it": "Indirizzo trovato nella I/O List con un FLD DIVERSO"},
    "cem_addr_none": {"en": "Address not found in the I/O List", "it": "Indirizzo non trovato nella I/O List"},
    "cem_fld_ok": {"en": "FLD found in the I/O List at a matching address",
                   "it": "FLD trovato nella I/O List all'indirizzo corrispondente"},
    "cem_fld_addr": {"en": "FLD found in the I/O List at a DIFFERENT address",
                     "it": "FLD trovato nella I/O List a un indirizzo DIVERSO"},
    "cem_fld_none": {"en": "FLD not found in the I/O List", "it": "FLD non trovato nella I/O List"},
    "cem_summary": {"en": "{refs} C&E references checked against the I/O List",
                    "it": "{refs} riferimenti C&E verificati rispetto alla I/O List"},
    # --- 140 cross-check IOL -> CEM ---
    "iol_cem_match": {"en": "Present in the Cause&Effect matrix; device and address match.",
                      "it": "Presente nella matrice Cause&Effect; dispositivo e indirizzo corrispondono."},
    "iol_cem_missing_mandatory": {"en": "Mandatory signal absent from the Cause&Effect matrix.",
                                  "it": "Segnale obbligatorio assente dalla matrice Cause&Effect."},
    "iol_cem_missing_safety": {"en": "Safety-related signal absent from the Cause&Effect matrix.",
                               "it": "Segnale di sicurezza assente dalla matrice Cause&Effect."},
    "iol_cem_missing_plain": {"en": "Not found in the Cause&Effect matrix.",
                              "it": "Non trovato nella matrice Cause&Effect."},
    "iol_cem_fld_only": {"en": "Present in the Cause&Effect matrix at a different address.",
                         "it": "Presente nella matrice Cause&Effect a un indirizzo diverso."},
    "iol_cem_addr_only": {"en": "Address present in the Cause&Effect matrix under a different device.",
                          "it": "Indirizzo presente nella matrice Cause&Effect con un dispositivo diverso."},
    "iol_cem_skipped": {"en": "Skipped - matches excluded word '{word}'.",
                        "it": "Ignorato - corrisponde alla parola esclusa '{word}'."},
    "iol_cem_unclassified": {"en": "Untyped, not safety-related - not cross-checked.",
                             "it": "Senza tipo, non legato alla sicurezza - non verificato."},
    "iol_cem_not_required": {"en": "Type not required in the Cause&Effect matrix - not cross-checked.",
                             "it": "Tipo non richiesto nella matrice Cause&Effect - non verificato."},
    "iol_cem_summary": {"en": "{checked} I/O signals checked against the Cause&Effect matrix",
                        "it": "{checked} segnali I/O verificati rispetto alla matrice Cause&Effect"},
    "iol_cem_skip_summary": {"en": "{skipped} signals skipped by the exclusion lists",
                             "it": "{skipped} segnali ignorati dalle liste di esclusione"},
}

_active = {"lang": "en"}                  # the ambient validation language (set per run by active_lang)


@contextmanager
def active_lang(lang):
    """Set the ambient finding language for the duration of a validation run, then restore it. The GUI
    runs one phase at a time, so the ambient is single-threaded; `en` is the default (parity)."""
    from pipeline4.core import i18n
    prev = _active["lang"]
    _active["lang"] = i18n.normalize(lang)
    try:
        yield
    finally:
        _active["lang"] = prev


def current_lang() -> str:
    return _active["lang"]


def msg(slug: str, **fmt) -> str:
    """The message for `slug` in the ACTIVE language (fallback EN), formatted with **fmt. Missing slug ->
    `<slug>` (loud). A bad/extra fmt key never crashes - the raw template is returned."""
    entry = MESSAGES.get(slug)
    if entry is None:
        return f"<{slug}>"
    template = entry.get(_active["lang"]) or entry.get("en") or f"<{slug}>"
    try:
        return template.format(**fmt)
    except (KeyError, IndexError, ValueError):
        return template
