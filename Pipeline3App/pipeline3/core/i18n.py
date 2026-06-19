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
