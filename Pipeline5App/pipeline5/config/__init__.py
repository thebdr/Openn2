"""Configuration - paths, project isolation, parameters, and the config-CSV loaders.

WHERE TO LOOK (the package split; every name re-exported here so `config.X` call sites are stable):

  paths.py    WHERE things live: APP_ROOT/SHARED, the active-project state (`use_project`), every
              directory helper (Database/, the output tree, the config-area subdirs). The TIA delivery
              dirs are transitional - they move to the Siemens system's output_layout at step 4.
  params.py   YAML parameters: project_params (`load_params`/`get_param`), the app-UI prefs
              (`load_app_ui` + `save_app_*`), the Documents-tab paths, generation params, the Files-tab
              structure, and sheet-pattern resolution (`resolve_sheet(s)`).
  loaders.py  The config-CSV readers (`read_config_csv` + `load_*`): classification rules, signal
              types, diagnosis, chain-reactions/interfaces, the DB registry, the DeviceTypesDatabase.

One module of state: `paths._PROJECT_ROOT` - everything else is pure functions over it.
"""
from pipeline5.config.paths import (  # noqa: F401
    APP_ROOT,
    SHARED,
    TEMPLATES_DIR,
    INTERFACE_TEMPLATE,
    BLOCK_TEMPLATES_DIR,
    DIAG_SCL_TEMPLATE,
    DEVICE_TYPES_DB_DEFAULT,
    COVERAGE_REPORT_STEM,
    VALIDATION_REPORT_STEM,
    VALIDATION_ERRORS_STEM,
    CHANGES_REPORT_STEM,
    use_project,
    use_builtin,
    active_project,
    config_project_dir,
    builtin_config_project_dir,
    database_dir,
    user_input_dir,
    output_root,
    blocks_import_dir,
    interfaces_dir,
    io_tags_dir,
    diaglist_dir,
    hardware_dir,
    blocks_creation_dir,
    coverage_dir,
    validation_report_dir,
    gui_log_dir,
    changes_report_dir,
    input_docs_dir,
    chain_reactions_dir,
    diagnosis_dir,
    datablocks_dir,
)
from pipeline5.config.params import (  # noqa: F401
    APP_FONT_SIZES,
    DOCUMENT_KEYS,
    js_to_re,
    as_sheet_list,
    resolve_sheets,
    resolve_sheet,
    params_file,
    app_config_file,
    builtin_app_config_file,
    generation_params_file,
    load_generation_params,
    load_files_tab,
    load_app_ui,
    save_app_font_size,
    save_app_language,
    save_app_theme,
    save_app_window_size,
    save_app_log_to_file,
    save_app_log_levels,
    load_document_paths,
    save_document_path,
    load_params,
    get_param,
    _resolve_font_size,
    _resolve_theme,
    _resolve_dim,
)
from pipeline5.config.loaders import (  # noqa: F401
    INTERFACE_CUSTOM_GAP,
    read_config_csv,
    load_column_map,
    load_change_weights,
    load_gate_rules,
    load_script_type_rules,
    load_signal_types,
    resolve_type,
    load_diagnosis_logic_rules,
    load_signal_diagnosis,
    load_diagnosis_columns,
    parse_params_by_type,
    load_device_types_db,
    load_interface_elements,
    load_interface_tagnames,
    load_db_definitions,
    load_db_elements,
    load_db_types,
)
