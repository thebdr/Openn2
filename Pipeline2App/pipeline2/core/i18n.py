"""Tiny hard-coded EN/IT string table for the validation messages and the GUI chrome.

No framework, no external files: two languages are foreseen, so the strings live inline.
`tr(key, lang, **fmt)` returns the localized string, `.format(**fmt)`-ed. Unknown keys fall
back to the key itself (so a missing translation is visible, never a crash).

Phase 0A check messages and GUI labels go through here. The pre-existing validation phases
(1/2/3) keep their English text for now; wrapping them is a mechanical follow-up.
"""
from __future__ import annotations

LANGUAGES = ("en", "it")
DEFAULT_LANG = "en"

# key -> {"en": ..., "it": ...}.  Placeholders use str.format syntax ({name}).
STRINGS: dict[str, dict[str, str]] = {
    # --- phase banners ----------------------------------------------------- #
    "phase_0a": {
        "en": "PHASE 0A - I/O List standalone validation",
        "it": "FASE 0A - Validazione autonoma I/O List",
    },
    "phase_0b": {
        "en": "PHASE 0B - Cause&Effect Matrix standalone validation",
        "it": "FASE 0B - Validazione autonoma Matrice Cause&Effect",
    },
    "no_checks_yet": {
        "en": "No checks implemented yet",
        "it": "Nessun controllo implementato al momento",
    },

    # --- missing / unreadable documents ------------------------------------ #
    "iolist_missing": {
        "en": "I/O List not found: {path}",
        "it": "I/O List non trovata: {path}",
    },
    "ce_missing": {
        "en": "Cause&Effect matrix not found: {path}",
        "it": "Matrice Cause&Effect non trovata: {path}",
    },
    "iolist_open_error": {
        "en": "Could not open the I/O List: {error}",
        "it": "Impossibile aprire la I/O List: {error}",
    },

    # --- Phase 0A: sheet selection ----------------------------------------- #
    "proc_sheet": {
        "en": "Processing sheet '{sheet}'",
        "it": "Elaborazione foglio '{sheet}'",
    },
    "skip_sheet": {
        "en": "Skipped sheet '{sheet}'",
        "it": "Foglio '{sheet}' ignorato",
    },
    "no_sheet": {
        "en": "No sheet found to process",
        "it": "Nessun foglio da elaborare trovato",
    },

    # --- Phase 0A: column header checks ------------------------------------ #
    "col_wrong": {
        "en": "Wrong column name '{actual}'. Correct name for column {n} is '{expected}'",
        "it": "Nome colonna errato '{actual}'. Il nome corretto per la colonna {n} è '{expected}'",
    },
    "col_unexpected": {
        "en": "Unexpected column name in column {n}: '{name}'",
        "it": "Nome colonna inatteso nella colonna {n}: '{name}'",
    },
    "col_duplicated": {
        "en": "Duplicated column name in column {n}: '{name}'",
        "it": "Nome colonna duplicato nella colonna {n}: '{name}'",
    },

    # --- Phase 0A: per-row content checks ---------------------------------- #
    "ip_error": {
        "en": "Error in the Profinet IP cell",
        "it": "Errore nella cella Profinet IP",
    },
    "ip_duplicated": {
        "en": "Duplicated IP {ip} (first seen at {first})",
        "it": "IP duplicato {ip} (già presente in {first})",
    },
    "dup_fld": {
        "en": "Duplicated Functional Unit + Location - Device (first seen at {first})",
        "it": "Unità Funzionale + Posizione - Dispositivo duplicati (già presente in {first})",
    },
    "fg_exclusion": {
        "en": "Column G has a value, so column F must be empty",
        "it": "La colonna G contiene un valore, quindi la colonna F deve essere vuota",
    },
    "address_wrong": {
        "en": "Invalid address format",
        "it": "Formato indirizzo non valido",
    },
    "pp_unknown": {
        "en": "Unknown permanent part '{value}'",
        "it": "Parte permanente sconosciuta '{value}'",
    },
    "pp_empty": {
        "en": "Empty permanent part",
        "it": "Parte permanente vuota",
    },
    "ts_missing": {
        "en": "T.S. ref is missing",
        "it": "Riferimento T.S. mancante",
    },
    "ip_missing": {
        "en": "IP address is missing",
        "it": "Indirizzo IP mancante",
    },
    "pname_wrong": {
        "en": "Invalid Profinet name (must start with 'n' and contain none of _ . / = *)",
        "it": "Nome Profinet non valido (deve iniziare con 'n' e non contenere _ . / = *)",
    },
    "too_many_nodes": {
        "en": "Too many nodes: {n} (max 126)",
        "it": "Troppi nodi: {n} (max 126)",
    },
    "nodes_over_64": {
        "en": "More than 64 nodes ({n}): this card cannot be used for induction line PH SYNCH / PH FEEDBACK",
        "it": "Più di 64 nodi ({n}): questa scheda non può essere usata per la linea a induzione PH SYNCH / PH FEEDBACK",
    },

    # --- Phase 1/2: cross-check messages (short, value-free; the table     -- #
    #     carries the values, the [FAIL]/[WARN]/[PASS] tag carries severity) - #
    # Phase 1 - C&E reference -> I/O List:
    "xc_p1_pass": {"en": "Reconciled against the I/O List.",
                   "it": "Riconciliato con la I/O List."},
    "xc_p1_fld": {"en": "Declared in the I/O List at a different address.",
                  "it": "Dichiarato nella I/O List a un indirizzo diverso."},
    "xc_p1_missing": {"en": "Device not declared in the I/O List.",
                      "it": "Dispositivo non dichiarato nella I/O List."},
    "xc_p1_empty": {"en": "Reference carries no device designation.",
                    "it": "Riferimento privo di designazione dispositivo."},
    # Phase 2 - I/O signal -> C&E coverage:
    "xc_p2_pass": {"en": "Present in the Cause&Effect matrix; device and address match.",
                   "it": "Presente nella matrice Cause&Effect; dispositivo e indirizzo corrispondono."},
    "xc_p2_missing_mandatory": {"en": "Mandatory signal absent from the Cause&Effect matrix.",
                                "it": "Segnale obbligatorio assente dalla matrice Cause&Effect."},
    "xc_p2_missing_safety": {"en": "Safety-related signal absent from the Cause&Effect matrix.",
                             "it": "Segnale di sicurezza assente dalla matrice Cause&Effect."},
    "xc_p2_missing_plain": {"en": "Not found in the Cause&Effect matrix.",
                            "it": "Non trovato nella matrice Cause&Effect."},
    "xc_p2_fld": {"en": "Present in the Cause&Effect matrix at a different address.",
                  "it": "Presente nella matrice Cause&Effect a un indirizzo diverso."},
    "xc_p2_addr": {"en": "Address present in the Cause&Effect matrix under a different device.",
                   "it": "Indirizzo presente nella matrice Cause&Effect sotto un dispositivo diverso."},

    # --- GUI: window titles / menus ---------------------------------------- #
    "app_title_designer": {"en": "I/O List Checker", "it": "Verifica I/O List"},
    "menu_file": {"en": "File", "it": "File"},
    "menu_language": {"en": "Language", "it": "Lingua"},
    "menu_new": {"en": "New project", "it": "Nuovo progetto"},
    "menu_open": {"en": "Open project…", "it": "Apri progetto…"},
    "menu_save": {"en": "Save project", "it": "Salva progetto"},
    "menu_save_as": {"en": "Save project as…", "it": "Salva progetto come…"},
    "menu_archive": {"en": "Archive project…", "it": "Archivia progetto…"},
    "menu_copy_inputs": {
        "en": "Copy input files into project on save",
        "it": "Copia i file di input nel progetto al salvataggio",
    },
    "menu_quit": {"en": "Quit", "it": "Esci"},

    # --- GUI: validation cascade buttons ----------------------------------- #
    "btn_run_all": {"en": "Run all", "it": "Esegui tutto"},
    "btn_validation": {"en": "Validation", "it": "Validazione"},
    "btn_iolist_validation": {"en": "I/O List Validation", "it": "Validazione I/O List"},
    "btn_ce_validation": {"en": "C&E Matrix Validation", "it": "Validazione Matrice C&E"},
    "btn_io_in_ce": {"en": "I/O presence in C&E Cross-Check",
                     "it": "Cross-Check presenza I/O nella C&E"},
    "btn_ce_in_io": {"en": "C&E presence in I/O Cross-Check",
                     "it": "Cross-Check presenza C&E nella I/O"},
    "btn_ce_in_iolist": {"en": "C&E in I/O List", "it": "C&E nella I/O List"},
    "btn_iolist_in_ce": {"en": "I/O List in C&E", "it": "I/O List nella C&E"},
    "btn_diagnosis": {"en": "Diagnosis", "it": "Diagnostica"},

    # --- GUI: config form section headers ---------------------------------- #
    "sec_iolist": {"en": "I/O List", "it": "I/O List"},
    "sec_ce": {"en": "Cause & Effect", "it": "Causa & Effetto"},
    "sec_rows": {"en": "Sheet rows (header / data)", "it": "Righe foglio (intestazione / dati)"},
    "sec_matrix_val": {"en": "Matrix validation", "it": "Validazione matrice"},

    # --- GUI: config form labels ------------------------------------------- #
    "lbl_iolist_file": {"en": "I/O List file", "it": "File I/O List"},
    "lbl_iolist_sheet": {"en": "I/O List sheets (regex)", "it": "Fogli I/O List (regex)"},
    "lbl_iolist_header": {"en": "I/O List header row", "it": "Riga intestazione I/O List"},
    "lbl_ce_file": {"en": "Cause&Effect file", "it": "File Cause&Effect"},
    "lbl_ce_sheet": {"en": "C&E matrix sheet (regex)", "it": "Foglio matrice C&E (regex)"},
    "lbl_ce_matrix_header": {"en": "C&E matrix header row", "it": "Riga intestazione matrice C&E"},
    "lbl_ce_matrix_data": {"en": "C&E matrix data row", "it": "Riga dati matrice C&E"},
    "lbl_area_header": {"en": "AREA header row", "it": "Riga intestazione AREA"},
    "lbl_area_data": {"en": "AREA data row", "it": "Riga dati AREA"},
    "lbl_areas": {"en": "Areas (regex/list)", "it": "Aree (regex/lista)"},
    "lbl_ce_fuzzy": {"en": "Fuzzy chars (Levenshtein)", "it": "Caratteri fuzzy (Levenshtein)"},
    "lbl_ce_mandatory": {"en": "Mandatory safety words", "it": "Parole di sicurezza obbligatorie"},
    "lbl_ce_excluded": {"en": "Excluded words", "it": "Parole escluse"},
    "lbl_ce_always_excluded": {"en": "Always-excluded words", "it": "Parole sempre escluse"},
    "lbl_ce_full_check": {"en": "Full check (ignore excluded)", "it": "Controllo completo (ignora escluse)"},
    "lbl_ce_full_print": {"en": "Log every PASS/SKIP", "it": "Registra ogni PASS/SKIP"},

    # --- GUI: buttons / status --------------------------------------------- #
    "btn_save": {"en": "Save", "it": "Salva"},
    "btn_reload": {"en": "Reload", "it": "Ricarica"},
    "btn_open_config": {"en": "Open config file", "it": "Apri file di configurazione"},
    "btn_open_output": {"en": "Open output", "it": "Apri output"},
    "btn_clear_log": {"en": "Clear log", "it": "Pulisci log"},
    "status_ready": {"en": "Ready", "it": "Pronto"},
    "status_running": {"en": "Running {phase}…", "it": "Esecuzione {phase}…"},
    "summary": {
        "en": "{passed} passed, {failed} failed, {warned} warning(s), {skipped} skipped",
        "it": "{passed} superati, {failed} falliti, {warned} avviso/i, {skipped} ignorati",
    },

    # --- GUI: archive popup ------------------------------------------------ #
    "archive_title": {"en": "Archive project", "it": "Archivia progetto"},
    "archive_name": {"en": "Archive name", "it": "Nome archivio"},
    "archive_add_datetime": {"en": "Append date/time", "it": "Aggiungi data/ora"},
    "archive_done": {"en": "Archive created: {path}", "it": "Archivio creato: {path}"},
    "btn_ok": {"en": "OK", "it": "OK"},
    "btn_cancel": {"en": "Cancel", "it": "Annulla"},

    # --- GUI: project status ----------------------------------------------- #
    "project_opened": {"en": "Project opened: {name}", "it": "Progetto aperto: {name}"},
    "project_saved": {"en": "Project saved: {name}", "it": "Progetto salvato: {name}"},
    "no_project": {"en": "(no project)", "it": "(nessun progetto)"},
}


def tr(key: str, lang: str = DEFAULT_LANG, **fmt) -> str:
    """Localized string for `key`, formatted with `**fmt`. Unknown key -> the key itself."""
    lang = lang if lang in LANGUAGES else DEFAULT_LANG
    entry = STRINGS.get(key)
    if entry is None:
        return key
    s = entry.get(lang) or entry.get(DEFAULT_LANG) or key
    if not fmt:
        return s
    try:
        return s.format(**fmt)
    except (KeyError, IndexError, ValueError):
        return s
