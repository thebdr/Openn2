"""Tiny hard-coded EN/IT string table for GUI chrome + validation messages.

No framework, no external files: two languages are foreseen, so the strings live inline.
`tr(key, lang, **fmt)` returns the localized string, `.format(**fmt)`-ed. Unknown keys fall
back to the key itself (so a missing translation is visible, never a crash). Grown per phase.
"""
from __future__ import annotations

LANGUAGES = ("en", "it")
DEFAULT_LANG = "en"

# key -> {"en": ..., "it": ...}. Placeholders use str.format syntax ({name}).
STRINGS: dict = {
    # --- run-all master + phase headers (assets/ButtonsLayout.xlsx row 3) ----------------- #
    "pb_run_pipeline": {"en": "Run Pipeline", "it": "Esegui Pipeline"},
    "ph_validation":   {"en": "Documents Validation", "it": "Validazione Documenti"},
    "ph_fill":         {"en": "Documents Fill Out", "it": "Compilazione Documenti"},
    "ph_staging":      {"en": "Documents Staging", "it": "Staging Documenti"},
    "ph_interfaces":   {"en": "Interfaces Generation", "it": "Generazione Interfacce"},
    "ph_signals":      {"en": "Signals Mapping", "it": "Mappatura Segnali"},
    "ph_diagnosis":    {"en": "Diagnosis Mapping", "it": "Mappatura Diagnostica"},
    "ph_hardware":     {"en": "Hardware Generation", "it": "Generazione Hardware"},
    "ph_software":     {"en": "Software Generation", "it": "Generazione Software"},
    "ph_reporting":    {"en": "Reporting", "it": "Reportistica"},

    # --- 100 Documents Validation --------------------------------------------------------- #
    "pb_validate_iolist": {"en": "Validate I/O List", "it": "Valida I/O List"},
    "pb_validate_ce":     {"en": "Validate C&E Matrix", "it": "Valida Matrice C&E"},
    "pb_xcheck_cem_iol":  {"en": "Cross-Check CEM->IOL", "it": "Verifica incrociata CEM->IOL"},
    "pb_xcheck_iol_cem":  {"en": "Cross-Check IOL->CEM", "it": "Verifica incrociata IOL->CEM"},
    "pb_validate_diag":   {"en": "Validate Diagnosis Assignments", "it": "Valida Assegnazioni Diagnostica"},
    "pb_open_errmgmt":    {"en": "Open Error Management .csv", "it": "Apri Error Management .csv"},
    "pb_open_iolist":     {"en": "Open I/O List", "it": "Apri I/O List"},
    "pb_open_ce":         {"en": "Open Cause&Effect Matrix", "it": "Apri Matrice Cause&Effect"},
    "pb_open_val_logs":   {"en": "Validation Logs Folder", "it": "Cartella Log di Validazione"},

    # --- 200 Documents Fill Out ----------------------------------------------------------- #
    "pb_fill_script_type":  {"en": "Fill IOList Script Type Column", "it": "Compila Colonna Script Type IOList"},
    "pb_fill_index":        {"en": "Fill IOList Index Column", "it": "Compila Colonna Index IOList"},
    "pb_fill_diag_cabinet": {"en": "Fill IOList Diag Cabinet Column", "it": "Compila Colonna Diag Cabinet IOList"},
    "pb_fill_diag_bit":     {"en": "Fill IOList Diag Bit Column", "it": "Compila Colonna Diag Bit IOList"},
    "pb_open_fill_config":  {"en": "Open Fill Config .csv", "it": "Apri Fill Config .csv"},
    "pb_open_signal_types": {"en": "Open Signal Types .csv", "it": "Apri Signal Types .csv"},

    # --- 300 Documents Staging ------------------------------------------------------------ #
    "pb_stage_iolist":    {"en": "Stage I/O List", "it": "Staging I/O List"},
    "pb_gen_io_database": {"en": "Generate IO Database", "it": "Genera IO Database"},
    "pb_open_io_database": {"en": "Open IO Database", "it": "Apri IO Database"},

    # --- 400 Interfaces Generation -------------------------------------------------------- #
    "pb_gen_interfaces":  {"en": "Generate Interfaces", "it": "Genera Interfacce"},
    "pb_open_interfaces": {"en": "Open Interfaces Folder", "it": "Apri Cartella Interfacce"},
    "pb_gen_custom_iface": {"en": "Generate Custom Interface ...", "it": "Genera Interfaccia Personalizzata ..."},

    # --- 500 Signals Mapping -------------------------------------------------------------- #
    "pb_gen_io_tags":     {"en": "Generate I/O Tags", "it": "Genera I/O Tags"},
    "pb_gen_data_blocks": {"en": "Generate Data Blocks", "it": "Genera Data Blocks"},
    "pb_open_io_tags":    {"en": "Open IO Tags", "it": "Apri IO Tags"},
    "pb_open_data_blocks": {"en": "Open Data Blocks Folder", "it": "Apri Cartella Data Blocks"},

    # --- 600 Diagnosis Mapping ------------------------------------------------------------ #
    "pb_gen_diag_list":     {"en": "Generate Diag List", "it": "Genera Diag List"},
    "pb_gen_diag_swblocks": {"en": "Generate Diag Software Blocks", "it": "Genera Diag Software Blocks"},
    "pb_open_diag_data":    {"en": "Open Diag Data Folder", "it": "Apri Cartella Diag Data"},
    "pb_open_diag_config":  {"en": "Open Diag Config .csv Folder", "it": "Apri Cartella Diag Config .csv"},

    # --- 700 Hardware Generation ---------------------------------------------------------- #
    "pb_gen_stations": {"en": "Generate Stations", "it": "Genera Stations"},
    "pb_gen_modules":  {"en": "Generate Modules", "it": "Genera Modules"},
    "pb_open_hardware": {"en": "Open Hardware Data Folder", "it": "Apri Cartella Hardware Data"},

    # --- 800 Software Generation ---------------------------------------------------------- #
    "pb_gen_shells":        {"en": "Generate Empty Shells .xlsm", "it": "Genera Empty Shells .xlsm"},
    "pb_gen_blocks":        {"en": "Generate Blocks", "it": "Genera Blocks"},
    "pb_gen_instances":     {"en": "Generate Instances", "it": "Genera Instances"},
    "pb_open_shells":       {"en": "Open Empty Shells .xlsm", "it": "Apri Empty Shells .xlsm"},
    "pb_open_blocks_folder": {"en": "Open Generated Blocks Folder", "it": "Apri Cartella Blocks Generati"},

    # --- 900 Reporting -------------------------------------------------------------------- #
    "pb_gen_cov_pipeline": {"en": "Generate Pipeline Coverage Report", "it": "Genera Report Copertura Pipeline"},
    "pb_gen_cov_tia":      {"en": "Generate Tia Portal Project Coverage Report",
                            "it": "Genera Report Copertura Progetto Tia Portal"},
    "pb_open_reports":     {"en": "Open Reports Folder", "it": "Apri Cartella Report"},

    # === Phase-100 validation messages (key = "v_<type>"; type = the log-type index + grep slug) ===
    # --- 110 Validate I/O List ------------------------------------------------------------ #
    "v_iolist_missing":  {"en": "I/O List not found: {path}", "it": "I/O List non trovata: {path}"},
    "v_iolist_locked":   {"en": "The I/O List may already be in use (open in Excel?) - close it and retry.",
                          "it": "La I/O List potrebbe essere gia in uso (aperta in Excel?) - chiuderla e riprovare."},
    "v_iolist_open_error": {"en": "Could not open the I/O List: {error}",
                            "it": "Impossibile aprire la I/O List: {error}"},
    "v_no_sheet":        {"en": "No I/O sheet matched {pattern}", "it": "Nessun foglio I/O corrisponde a {pattern}"},
    "v_proc_sheet":      {"en": "Processing sheet '{sheet}'", "it": "Elaborazione foglio '{sheet}'"},
    "v_skip_sheet":      {"en": "Skipped sheet '{sheet}'", "it": "Foglio ignorato '{sheet}'"},
    "v_col_wrong":       {"en": "Wrong column name '{actual}'. Correct name for column {n} is '{expected}'",
                          "it": "Nome colonna errato '{actual}'. Il nome corretto per la colonna {n} e '{expected}'"},
    "v_col_unexpected":  {"en": "Unexpected column name in column {n}: '{name}'",
                          "it": "Nome colonna inatteso nella colonna {n}: '{name}'"},
    "v_col_duplicated":  {"en": "Duplicated column name in column {n}: '{name}'",
                          "it": "Nome colonna duplicato nella colonna {n}: '{name}'"},
    "v_ip_error":        {"en": "Error in the Profinet IP cell", "it": "Errore nella cella IP Profinet"},
    "v_ip_duplicated":   {"en": "Duplicated IP {ip} (first seen at {first})",
                          "it": "IP duplicato {ip} (prima occorrenza in {first})"},
    "v_dup_fld":         {"en": "Duplicated Functional unit + Location + Device (first seen at {first})",
                          "it": "Functional unit + Location + Device duplicati (prima occorrenza in {first})"},
    "v_fg_exclusion":    {"en": "Column G has a value, so column F must be empty",
                          "it": "La colonna G ha un valore, quindi la colonna F deve essere vuota"},
    "v_addr_format":     {"en": "Invalid address format", "it": "Formato indirizzo non valido"},
    "v_pp_empty":        {"en": "Empty permanent part", "it": "Parte permanente vuota"},
    "v_pp_unknown":      {"en": "Unknown permanent part '{value}'", "it": "Parte permanente sconosciuta '{value}'"},
    "v_ts_missing":      {"en": "T.S. ref is missing", "it": "Riferimento T.S. mancante"},
    "v_ip_missing":      {"en": "IP address is missing", "it": "Indirizzo IP mancante"},
    "v_pname_wrong":     {"en": "Invalid Profinet name (must start with 'n' and contain none of _ . / = *)",
                          "it": "Nome Profinet non valido (deve iniziare con 'n' e non contenere _ . / = *)"},
    "v_nodes_over_64":   {"en": "More than 64 nodes ({n}): this card cannot drive induction-line PH SYNCH / PH FEEDBACK",
                          "it": "Piu di 64 nodi ({n}): questa scheda non puo gestire PH SYNCH / PH FEEDBACK della linea a induzione"},
    "v_too_many_nodes":  {"en": "Too many nodes: {n} (max 126)", "it": "Troppi nodi: {n} (max 126)"},
    "v_struck_row":      {"en": "Row is struck through (excluded by policy)", "it": "Riga barrata (esclusa dalla policy)"},
    "v_iolist_summary":  {"en": "{sheets} sheet(s) processed, {nodes} node(s)",
                          "it": "{sheets} foglio/i elaborati, {nodes} nodo/i"},
    "v_row_ok":          {"en": "All checks passed", "it": "Tutti i controlli superati"},

    # --- 120 Validate C&E Matrix ---------------------------------------------------------- #
    "v_ce_absent":       {"en": "Cause&Effect matrix not configured/found - C&E checks skipped",
                          "it": "Matrice Cause&Effect non configurata/trovata - verifiche C&E ignorate"},
    "v_ce_locked":       {"en": "The Cause&Effect matrix may already be in use (open in Excel?) - close it and retry.",
                          "it": "La matrice Cause&Effect potrebbe essere gia in uso (aperta in Excel?) - chiuderla e riprovare."},
    "v_ce_sheet_missing": {"en": "C&E matrix sheet not found: {sheet}", "it": "Foglio matrice C&E non trovato: {sheet}"},
    "v_matrix_addr_kind": {"en": "Output/internal address {addr} on the CAUSE&EFFECT MATRIX (inputs only)",
                           "it": "Indirizzo di uscita/interno {addr} nella CAUSE&EFFECT MATRIX (solo ingressi)"},
    "v_area_addr_kind":  {"en": "Input address {addr} on an AREA sheet (outputs only)",
                          "it": "Indirizzo di ingresso {addr} in un foglio AREA (solo uscite)"},
    "v_dup_addr":        {"en": "Duplicated address {addr} within the sheet (first seen at {first})",
                          "it": "Indirizzo duplicato {addr} nel foglio (prima occorrenza in {first})"},
    "v_ce_summary":      {"en": "{refs} address reference(s) checked across {sheets} sheet(s)",
                          "it": "{refs} riferimenti di indirizzo verificati su {sheets} foglio/i"},

    # --- 130 Cross-Check CEM->IOL --------------------------------------------------------- #
    "v_cem_ref_empty":   {"en": "Reference carries no device designation",
                          "it": "Il riferimento non riporta alcun dispositivo"},
    "v_cem_dev_missing": {"en": "Device not declared in the I/O List",
                          "it": "Dispositivo non dichiarato nella I/O List"},
    "v_cem_fld_addr_mismatch": {"en": "Declared in the I/O List at a different address",
                                "it": "Dichiarato nella I/O List a un indirizzo diverso"},
    "v_cem_match":       {"en": "Reconciled against the I/O List", "it": "Riconciliato con la I/O List"},
    "v_cem_summary":     {"en": "{refs} C&E reference(s) checked against the I/O List",
                          "it": "{refs} riferimenti C&E verificati rispetto alla I/O List"},

    # --- 140 Cross-Check IOL->CEM --------------------------------------------------------- #
    "v_iol_cem_match":   {"en": "Present in the Cause&Effect matrix; device and address match.",
                          "it": "Presente nella matrice Cause&Effect; dispositivo e indirizzo corrispondono."},
    "v_iol_cem_missing_mandatory": {"en": "Mandatory signal absent from the Cause&Effect matrix.",
                                    "it": "Segnale obbligatorio assente dalla matrice Cause&Effect."},
    "v_iol_cem_missing_safety": {"en": "Safety-related signal absent from the Cause&Effect matrix.",
                                 "it": "Segnale di sicurezza assente dalla matrice Cause&Effect."},
    "v_iol_cem_missing_plain": {"en": "Not found in the Cause&Effect matrix.",
                                "it": "Non trovato nella matrice Cause&Effect."},
    "v_iol_cem_fld_only": {"en": "Present in the Cause&Effect matrix at a different address.",
                           "it": "Presente nella matrice Cause&Effect a un indirizzo diverso."},
    "v_iol_cem_addr_only": {"en": "Address present in the Cause&Effect matrix under a different device.",
                            "it": "Indirizzo presente nella matrice Cause&Effect con un dispositivo diverso."},
    "v_iol_cem_skipped": {"en": "Skipped - matches excluded word '{word}'.",
                          "it": "Ignorato - corrisponde alla parola esclusa '{word}'."},
    "v_iol_cem_unclassified": {"en": "Untyped, not safety-related - not cross-checked.",
                               "it": "Senza tipo, non legato alla sicurezza - non verificato."},
    "v_iol_cem_not_required": {"en": "Type not required in the Cause&Effect matrix - not cross-checked.",
                               "it": "Tipo non richiesto nella matrice Cause&Effect - non verificato."},
    "v_iol_cem_summary": {"en": "{checked} I/O signal(s) checked against the Cause&Effect matrix",
                          "it": "{checked} segnali I/O verificati rispetto alla matrice Cause&Effect"},
    "v_iol_cem_skip_summary": {"en": "{skipped} signal(s) skipped by the exclusion lists",
                               "it": "{skipped} segnali ignorati dalle liste di esclusione"},

    # --- 150 Validate Diagnosis Assignments ----------------------------------------------- #
    "v_diag_invalid":    {"en": "In-diagnosis signal has missing/invalid {fields}",
                          "it": "Segnale in diagnostica con {fields} mancante/non valido"},
    "v_diag_unique":     {"en": "Diagnosis slot {slot} is unique", "it": "Slot diagnostica {slot} univoco"},
    "v_diag_dup_slot":   {"en": "Duplicate diagnosis slot {slot} - also at {others}",
                          "it": "Slot diagnostica duplicato {slot} - anche in {others}"},
    "v_diag_summary":    {"en": "{n} in-diagnosis signal(s) checked", "it": "{n} segnali in diagnostica verificati"},
}


def tr(key: str, lang: str = DEFAULT_LANG, **fmt) -> str:
    """Localized string for `key`. Unknown key -> the key itself. `fmt` is applied via str.format."""
    entry = STRINGS.get(key)
    if not entry:
        text = key
    else:
        text = entry.get(lang) or entry.get(DEFAULT_LANG) or key
    if fmt:
        try:
            return text.format(**fmt)
        except (KeyError, IndexError, ValueError):
            return text
    return text
