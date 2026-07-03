"""Tiny hard-coded EN/IT string table for the GUI chrome (a clean-room port of PL3's `core/i18n.py`).

No framework, no external files: two languages are foreseen, so the strings live inline.
`tr(key, lang, **fmt)` returns the localized string, `.format(**fmt)`-ed. An unknown key falls back to
the key itself (so a missing translation is visible, never a crash). The phase-bar labels live here as
KEYS (`gui/phases.py` carries `name_key`/`label_key`, not English literals); the registry STRUCTURE
(numbers/kinds/sections/handlers) stays in the registry.

SCOPE: this covers the persistent CHROME (the phase bar, toolbar, notebook tabs, the status bar). The
transient run-log NARRATIVE (PHASE banners with sub-detail, PASS/progress lines) stays English, matching
PL3 (its generators emit untranslated progress strings); the validation finding text lives in
`domain/validation/messages.py`.
"""
from __future__ import annotations

LANGUAGES = ("en", "it")
DEFAULT_LANG = "en"

# key -> {"en": ..., "it": ...}. Placeholders use str.format syntax ({name}). EN text == the labels the
# rework's registry showed verbatim (so toggling to EN changes nothing); IT from PL3 + new translations.
STRINGS: dict = {
    # --- run-all master + phase headers (assets/ButtonsLayout.xlsx row 3) ------------------ #
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
    "pb_change_report":   {"en": "Before/After Quality Report", "it": "Report Qualita Prima/Dopo"},
    "pb_validate_diag":   {"en": "Validate Diagnosis Assignments", "it": "Valida Assegnazioni Diagnostica"},
    "pb_clean_iolist":    {"en": "Clean IOList Addresses & FLD", "it": "Pulisci Indirizzi & FLD IOList"},
    "pb_clean_cematrix":  {"en": "Clean CEMatrix Addresses & FLD", "it": "Pulisci Indirizzi & FLD Matrice C&E"},
    "pb_open_errmgmt":    {"en": "Open Error Management .csv", "it": "Apri Error Management .csv"},
    "pb_open_iolist":     {"en": "Open I/O List", "it": "Apri I/O List"},
    "pb_open_ce":         {"en": "Open Cause&Effect Matrix", "it": "Apri Matrice Cause&Effect"},
    "pb_open_val_logs":   {"en": "Validation Logs Folder", "it": "Cartella Log di Validazione"},

    # --- 200 Documents Fill Out (built + wired; the 200 button, kept out of Run-all by design) ---- #
    "pb_fill_script_type":  {"en": "Fill IOList Script Type Column", "it": "Compila Colonna Script Type IOList"},
    "pb_fill_index":        {"en": "Fill IOList Index Column", "it": "Compila Colonna Index IOList"},
    "pb_risky_index":       {"en": "Risky Index Fill (review)", "it": "Compila Index Rischioso (rivedi)"},
    "pb_fill_diag_cabinet": {"en": "Fill IOList Diag Cabinet Column", "it": "Compila Colonna Diag Cabinet IOList"},
    "pb_fill_diag_bit":     {"en": "Fill IOList Diag Bit Column", "it": "Compila Colonna Diag Bit IOList"},
    "pb_open_fill_config":  {"en": "Open Fill Config .csv", "it": "Apri Fill Config .csv"},
    "pb_open_signal_types": {"en": "Open Signal Types .csv", "it": "Apri Signal Types .csv"},

    # --- 300 Documents Staging ------------------------------------------------------------ #
    "pb_stage_iolist":     {"en": "Stage I/O List", "it": "Staging I/O List"},
    "pb_stage_cematrix":   {"en": "Stage C&E Matrix", "it": "Staging Matrice C&E"},
    "pb_open_io_database": {"en": "Open IO Database", "it": "Apri IO Database"},

    # --- 400 Interfaces Generation -------------------------------------------------------- #
    "pb_gen_interfaces":   {"en": "Generate Interfaces", "it": "Genera Interfacce"},
    "pb_open_interfaces":  {"en": "Open Interfaces Folder", "it": "Apri Cartella Interfacce"},
    "pb_gen_custom_iface": {"en": "Generate Custom Interface …", "it": "Genera Interfaccia Personalizzata …"},

    # --- 500 Signals Mapping -------------------------------------------------------------- #
    "pb_gen_io_tags":      {"en": "Generate I/O Tags", "it": "Genera I/O Tags"},
    "pb_gen_data_blocks":  {"en": "Generate Data Blocks", "it": "Genera Data Blocks"},
    "pb_open_io_tags":     {"en": "Open IO Tags", "it": "Apri IO Tags"},
    "pb_open_data_blocks": {"en": "Open Data Blocks Folder", "it": "Apri Cartella Data Blocks"},

    # --- 600 Diagnosis Mapping ------------------------------------------------------------ #
    "pb_gen_diag_list":     {"en": "Generate Diag List", "it": "Genera Diag List"},
    "pb_gen_diag_swblocks": {"en": "Generate Diag Software Blocks", "it": "Genera Diag Software Blocks"},
    "pb_open_diag_data":    {"en": "Open Diag Data Folder", "it": "Apri Cartella Diag Data"},
    "pb_open_diag_config":  {"en": "Open Diag Config .csv Folder", "it": "Apri Cartella Diag Config .csv"},

    # --- 700 Hardware Generation ---------------------------------------------------------- #
    "pb_gen_stations":  {"en": "Generate Stations", "it": "Genera Stations"},
    "pb_gen_modules":   {"en": "Generate Modules", "it": "Genera Modules"},
    "pb_open_hardware": {"en": "Open Hardware Data Folder", "it": "Apri Cartella Hardware Data"},

    # --- 800 Software Generation ---------------------------------------------------------- #
    "pb_gen_shells":         {"en": "Generate Empty Shells .xlsm", "it": "Genera Empty Shells .xlsm"},
    "pb_gen_blocks":         {"en": "Generate Blocks", "it": "Genera Blocks"},
    "pb_gen_instances":      {"en": "Generate Instances", "it": "Genera Instances"},
    "pb_open_builder_shells": {"en": "Open Builder Shells .xlsm", "it": "Apri Builder Shells .xlsm"},
    "pb_open_blocks_folder": {"en": "Open Generated Blocks Folder", "it": "Apri Cartella Blocks Generati"},

    # --- 900 Reporting -------------------------------------------------------------------- #
    "pb_gen_cov_pipeline": {"en": "Generate Pipeline Coverage Report", "it": "Genera Report Copertura Pipeline"},
    "pb_gen_cov_tia":      {"en": "Generate TIA Project Coverage Report",
                            "it": "Genera Report Copertura Progetto TIA"},
    "pb_open_reports":     {"en": "Open Reports Folder", "it": "Apri Cartella Report"},

    # --- toolbar / notebook tabs / status bar (chrome) ------------------------------------ #
    "tb_theme":     {"en": "Theme", "it": "Tema"},
    "tb_clear_log": {"en": "Clear Log", "it": "Pulisci Log"},
    "tb_levels":    {"en": "Levels", "it": "Livelli"},
    "tb_font":      {"en": "Font", "it": "Carattere"},
    "tb_lang":      {"en": "Lang", "it": "Lingua"},
    "tb_log_to_file": {"en": "Log to file", "it": "Log su file"},
    "tb_project":   {"en": "Project", "it": "Progetto"},
    "pm_builtin":   {"en": "builtin (Shared)", "it": "predefinito (Shared)"},
    "pm_new":       {"en": "New Project", "it": "Nuovo progetto"},
    "pm_new_parent": {"en": "Choose the parent folder for the new project", "it": "Scegli la cartella per il nuovo progetto"},
    "pm_new_name":  {"en": "Project name:", "it": "Nome progetto:"},
    "pm_open":      {"en": "Open Project", "it": "Apri progetto"},
    "pm_recent":    {"en": "Recent", "it": "Recenti"},
    "pm_no_recent": {"en": "(no recent projects)", "it": "(nessun progetto recente)"},
    "pm_set_root":  {"en": "Set projects root", "it": "Imposta cartella progetti"},
    "pm_archive":   {"en": "Archive Project…", "it": "Archivia progetto…"},
    "pm_archived":  {"en": "archived {n} files -> {path}", "it": "archiviati {n} file -> {path}"},
    "pm_close":     {"en": "Close Project (use builtin)", "it": "Chiudi progetto (usa predefinito)"},
    # --- the New Project dialog ------------------------------------------------------------ #
    "np_title":     {"en": "New project", "it": "Nuovo progetto"},
    "np_type":      {"en": "Project type", "it": "Tipo di progetto"},
    "np_multi":     {"en": "Multi-System Controller (select more than one type)",
                     "it": "Controllore multi-sistema (seleziona più di un tipo)"},
    "np_name":      {"en": "Project name", "it": "Nome progetto"},
    "np_base":      {"en": "Base folder", "it": "Cartella base"},
    "np_path":      {"en": "Project path", "it": "Percorso progetto"},
    "np_backups":   {"en": "Backups kept (0-20)", "it": "Backup conservati (0-20)"},
    "np_backups_hint": {"en": "each phase run backs the full project up beside it; "
                              "editable later in project_params.yaml (project.backups_kept)",
                        "it": "ogni fase esegue un backup completo del progetto accanto ad esso; "
                              "modificabile in project_params.yaml (project.backups_kept)"},
    "np_create":    {"en": "Create", "it": "Crea"},
    "np_cancel":    {"en": "Cancel", "it": "Annulla"},
    "np_err_no_type": {"en": "select at least one available project type",
                       "it": "seleziona almeno un tipo di progetto disponibile"},
    "np_err_no_base": {"en": "pick the base folder", "it": "scegli la cartella base"},
    "tab_log":      {"en": "Log", "it": "Log"},
    "tab_files":    {"en": "Files", "it": "File"},
    "tab_findings": {"en": "Findings", "it": "Esiti"},
    "tab_explorer": {"en": "Database Explorer", "it": "Esplora Database"},
    "tab_documents": {"en": "Documents", "it": "Documenti"},
    "st_ready":     {"en": "Ready", "it": "Pronto"},
    "st_language":  {"en": "language: {code}", "it": "lingua: {code}"},
    "st_running":   {"en": "a phase is already running - wait for it to finish",
                     "it": "una fase è già in esecuzione - attendere il termine"},

    # --- Documents tab (the 4 input-document file pickers) --------------------------------- #
    "doc_intro":       {"en": "The project's input documents. Set the current revision and the prior "
                              "revision (the prior feeds the ph100 before/after report).",
                        "it": "I documenti di input del progetto. Imposta la revisione corrente e quella "
                              "precedente (la precedente alimenta il report prima/dopo della fase 100)."},
    "doc_sec_current":  {"en": "Current documents", "it": "Documenti correnti"},
    "doc_sec_previous": {"en": "Previous revision (feeds the ph100 before/after report)",
                         "it": "Revisione precedente (alimenta il report prima/dopo della fase 100)"},
    "doc_iolist":      {"en": "I/O List (current)", "it": "I/O List (corrente)"},
    "doc_iolist_prev": {"en": "I/O List (previous)", "it": "I/O List (precedente)"},
    "doc_matrix":      {"en": "C&E Matrix (current)", "it": "Matrice C&E (corrente)"},
    "doc_matrix_prev": {"en": "C&E Matrix (previous)", "it": "Matrice C&E (precedente)"},
    "doc_browse":      {"en": "Browse…", "it": "Sfoglia…"},
    "doc_clear":       {"en": "Clear", "it": "Cancella"},
    "doc_not_set":     {"en": "(not set)", "it": "(non impostato)"},
    "doc_picker_title": {"en": "Select the document", "it": "Seleziona il documento"},
    "doc_import":      {"en": "Import documents into the project folder",
                        "it": "Importa i documenti nella cartella progetto"},
    "doc_import_done": {"en": "documents import: {done}", "it": "importazione documenti: {done}"},
    "doc_import_none": {"en": "nothing to import (no documents set)",
                        "it": "niente da importare (nessun documento impostato)"},
    "doc_import_no_project": {"en": "no project open - create/open a project first",
                              "it": "nessun progetto aperto - crea/apri prima un progetto"},
    "doc_set":         {"en": "set {doc}", "it": "{doc} impostato"},
    "doc_cleared":     {"en": "cleared {doc}", "it": "{doc} cancellato"},

    # --- validation report chrome (the .html title + summary; the finding lines localize at build) --- #
    "rpt_errors_only": {"en": "errors only", "it": "solo errori"},
    "rpt_summary":     {"en": "{p} passed, {f} failed, {w} warnings, {s} skipped",
                        "it": "{p} superati, {f} falliti, {w} avvisi, {s} ignorati"},
}


def tr(key: str, lang: str = DEFAULT_LANG, **fmt) -> str:
    """Localized string for `key`. Unknown key -> the key itself. `fmt` is applied via str.format."""
    entry = STRINGS.get(key)
    text = (entry.get(lang) or entry.get(DEFAULT_LANG) or key) if entry else key
    if fmt:
        try:
            return text.format(**fmt)
        except (KeyError, IndexError, ValueError):
            return text
    return text


def normalize(lang) -> str:
    """Coerce an arbitrary value to a supported language code (default `en`)."""
    code = str(lang or "").strip().lower()
    return code if code in LANGUAGES else DEFAULT_LANG
