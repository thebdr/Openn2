"""PL4 configuration: paths, project isolation, and sheet-name resolution.

The CSV / JSON-cell loaders are added here as the phases that need them are ported. The top-level
**Database/** folder (the SSOT - DESIGN 10.3) and the **Output/** tree (the OPn `BuilderData/` export
surface) both follow the active project (`use_project`) or default to `Shared/` (the builtin), so the
whole app is project-isolated with no special-casing downstream.
"""
from __future__ import annotations

import csv
import os
import re
import sys

# APP_ROOT = the Pipeline4App dir (dev: this file's great-grandparent; frozen: the bundle dir).
if getattr(sys, "frozen", False):
    APP_ROOT = getattr(sys, "_MEIPASS", None) or os.path.dirname(sys.executable)
else:
    # pipeline4/core/config.py -> core -> pipeline4 -> Pipeline4App
    APP_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SHARED = os.path.normpath(os.path.join(APP_ROOT, os.pardir, "Shared"))
TEMPLATES_DIR = os.path.join(SHARED, "Templates")
INTERFACE_TEMPLATE = os.path.join(TEMPLATES_DIR, "MachineInterfaces", "TEMPLATE_INTERFACES_v0.0.xlsx")
BLOCK_TEMPLATES_DIR = os.path.join(TEMPLATES_DIR, "Tia Portal Software Blocks")   # ph800 block .xml templates
DIAG_SCL_TEMPLATE = os.path.join(BLOCK_TEMPLATES_DIR, "TEMPLATE--v1.0--06_Diagnostic for OPC.scl")
_BUILTIN_CONFIG_PROJECT = os.path.join(APP_ROOT, "config_project")
_BUILTIN_DATABASE = os.path.join(SHARED, "Database")        # the SSOT folder (DESIGN 10.3)
_BUILTIN_OUTPUT = os.path.join(SHARED, "OutputTree")        # the OPn BuilderData export surface
DEVICE_TYPES_DB_DEFAULT = os.path.join(SHARED, "HardwareConfigBuilderData", "DeviceTypesDatabase.csv")  # ph700 DTD

# The ACTIVE project root (None = the builtin app config + Shared/). Project open/close calls
# use_project() so the config loaders, the Database folder, and the Output tree all follow the project.
_PROJECT_ROOT: str | None = None


def use_project(root: str | None) -> None:
    """Point the config loaders + the Database + the Output tree at <root>/...; None reverts to builtin."""
    global _PROJECT_ROOT
    _PROJECT_ROOT = root or None


def use_builtin() -> None:
    use_project(None)


def active_project() -> str | None:
    return _PROJECT_ROOT


def config_project_dir() -> str:
    return os.path.join(_PROJECT_ROOT, "config_project") if _PROJECT_ROOT else _BUILTIN_CONFIG_PROJECT


def builtin_config_project_dir() -> str:
    """The app's BUNDLED canonical config_project (always, regardless of the active project). It is the
    completeness reference a project's config_project is verified against (project/assert_config_complete)."""
    return _BUILTIN_CONFIG_PROJECT


def database_dir() -> str:
    """The top-level Database/ folder - the SSOT (one CSV-with-JSON-cells per table)."""
    return os.path.join(_PROJECT_ROOT, "Database") if _PROJECT_ROOT else _BUILTIN_DATABASE


def user_input_dir() -> str:
    """The USER-LOCAL inputs (the treatment registry error_management.csv) - per project when one is open,
    else the builtin config_project's. Co-located with the active config so each project owns its treatments."""
    return os.path.join(config_project_dir(), "user_input")


def output_root() -> str:
    """The BuilderData/ export root - what OPn imports."""
    return os.path.join(_PROJECT_ROOT, "Output") if _PROJECT_ROOT else _BUILTIN_OUTPUT


def blocks_import_dir() -> str:
    """The phase-520 GlobalDB-XML BuilderData surface (`<DB>.xml`), under the output root - what OP4
    imports. Byte-stable to PL3's `ImportReady/` (the 02_COM.xml there is phase-800-owned)."""
    return os.path.join(output_root(), "TiaPortalProjectInterface", "BuilderData", "SoftwareBlocks", "ImportReady")


def interfaces_dir() -> str:
    """The phase-400 `IF_*.xlsx` output - DOCUMENTATION/intermediate under ProjectDocumentation, NOT a
    BuilderData import surface (510 reads the IF_ sheets inserted into the I/O List, not these files)."""
    return os.path.join(output_root(), "ProjectDocumentation", "InformationDatabase", "Interfaces")


def io_tags_dir() -> str:
    """The phase-510 I/O Tags BuilderData surface (`PLCTags.xlsx`), under the output root - what OP4
    imports. The leaf is `PlcTags` to match PL3's OUTPUT_PATHS['io_tags_dir'] (the OP-import contract path)."""
    return os.path.join(output_root(), "TiaPortalProjectInterface", "BuilderData", "PlcTags")


def diaglist_dir() -> str:
    """The phase-610 DiagList output (`DiagList_IO.csv` + `DiagList_Logic.csv`) - DOCUMENTATION under
    ProjectDocumentation (NOT a BuilderData import surface; matches PL3's DiagnosisData path)."""
    return os.path.join(output_root(), "ProjectDocumentation", "InformationDatabase", "DiagnosisData")


def hardware_dir() -> str:
    """The phase-700 Hardware BuilderData surface (`Stations.csv` + `Modules.csv`), under the output root
    - what OP4 imports. Matches PL3's OUTPUT_PATHS['hardware_dir'] (the OP-import contract path)."""
    return os.path.join(output_root(), "TiaPortalProjectInterface", "BuilderData", "HardwareConfiguration")


def blocks_creation_dir() -> str:
    """The phase-800 Software CreationInfo BuilderData surface (the `$/#/%/@` template-fill CSVs +
    `InstanceDBs.csv`), under the output root - what OP4 imports. Matches PL3's `blocks_creation_dir`."""
    return os.path.join(output_root(), "TiaPortalProjectInterface", "BuilderData", "SoftwareBlocks", "CreationInfo")


def coverage_dir() -> str:
    """The phase-900 coverage report output (`io_project_coverage_report.{csv,txt}`) - DOCUMENTATION under
    ProjectDocumentation/Reports, NOT a BuilderData import surface (matches PL3's `Reports/` placement)."""
    return os.path.join(output_root(), "ProjectDocumentation", "Reports")


COVERAGE_REPORT_STEM = "io_project_coverage_report"   # the phase-900 report base name (+ .csv / .txt)


def validation_report_dir() -> str:
    """The phase-100 validation reports (`documents_validation_report`/`_errors`.{txt,html}) - DOCUMENTATION
    under ProjectDocumentation/Reports (same tree as the coverage report; NOT a BuilderData surface)."""
    return os.path.join(output_root(), "ProjectDocumentation", "Reports")


VALIDATION_REPORT_STEM = "documents_validation_report"   # phase-100 complete report (+ .txt / .html)
VALIDATION_ERRORS_STEM = "documents_validation_errors"   # phase-100 errors-only report (+ .txt / .html)


def gui_log_dir() -> str:
    """Where the GUI's optional 'log to file' tee writes (`pl4_log_<stamp>.txt`) - a Logs/ subfolder of the
    reports tree."""
    return os.path.join(validation_report_dir(), "Logs")


def changes_report_dir() -> str:
    """The ph100 before/after quality report (`io_documents_quality_report.html` + `.csv`) - DOCUMENTATION
    under ProjectDocumentation/Reports (same tree as the validation/coverage reports; NOT a BuilderData
    surface). The report is a STANDALONE analysis (not part of the pipeline)."""
    return os.path.join(output_root(), "ProjectDocumentation", "Reports")


CHANGES_REPORT_STEM = "io_documents_quality_report"      # the ph100 before/after report base (+ .html / .csv)


# --- sheet-name resolution (regex / JS-literal, case-insensitive) -------------------------------- #
def js_to_re(pattern: str) -> str:
    """Accept a JS-style regex literal ('/pattern/flags' or 'pattern/flags') and return the bare Python
    pattern (flags stripped; matching is case-insensitive anyway). A plain pattern / literal sheet name
    is returned unchanged. (Backslash regexes must be SINGLE-quoted in YAML.)"""
    text = str(pattern or "").strip()
    match = re.match(r"^/?(.*)/([gimsuxy]+)$", text)        # only strip when real trailing flag letters
    if match:
        return match.group(1)
    if len(text) >= 2 and text.startswith("/") and text.endswith("/"):
        return text[1:-1]
    return text


def as_sheet_list(patterns) -> list:
    """Normalize a sheet pattern (one string, or a list/tuple of them) to a list of pattern strings."""
    if patterns is None:
        return []
    if isinstance(patterns, (list, tuple)):
        return [str(p) for p in patterns if str(p).strip()]
    return [str(patterns)] if str(patterns).strip() else []


def resolve_sheets(patterns, available) -> list:
    """Match sheet-name `patterns` (each a regex, case-insensitive `re.search`; JS '/.../flags' accepted;
    an invalid regex falls back to an exact case-insensitive name match) against the workbook's
    `available` sheet names. Returns matching names in workbook order, de-duplicated."""
    compiled = []
    for pattern in as_sheet_list(patterns):
        bare = js_to_re(pattern)
        try:
            compiled.append(("re", re.compile(bare, re.IGNORECASE)))
        except re.error:
            compiled.append(("lit", bare.lower()))
    matched = []
    for name in available:
        for kind, value in compiled:
            if (value.search(name) if kind == "re" else value == name.lower()):
                matched.append(name)
                break
    return matched


def resolve_sheet(pattern, available):
    """The first sheet name matching `pattern`, or None (single-sheet contexts e.g. the C&E matrix)."""
    matched = resolve_sheets(pattern, available)
    return matched[0] if matched else None


# --- project params (the nested project_params.yaml schema) -------------------------------------- #
def _read_yaml(path: str) -> dict:
    """Parse a YAML file to plain dicts/lists ({} if empty). Single-quoted values (the JS-style sheet
    regexes) are taken literally - no escape processing - so a '\\d' survives."""
    from ruamel.yaml import YAML
    parser = YAML(typ="safe")
    with open(path, encoding="utf-8") as handle:
        return parser.load(handle) or {}


def _resolve_path(base: str, value) -> str:
    """A path relative to `base` -> absolute (normalized); an absolute or blank path is returned as-is."""
    text = str(value or "").strip()
    if not text or os.path.isabs(text):
        return text
    return os.path.normpath(os.path.join(base, text))


def params_file() -> str:
    """The active project params file (the builtin config_project/ or the open project's)."""
    return os.path.join(config_project_dir(), "project_params.yaml")


def app_config_file() -> str:
    """The COSMETIC GUI launch config (app_config.yaml) - tracked, NOT per-project run params."""
    return os.path.join(config_project_dir(), "app_config.yaml")


def builtin_app_config_file() -> str:
    """The BUILTIN app_config.yaml - the home of the `user_interface` block. UI preferences
    (language, log levels, theme, font, window size, tee) are APP/user-scoped, NOT project-scoped:
    they must load and save against the SAME file no matter which project is open. (The launch-time
    read also happens BEFORE auto_reopen, so an active-file save would silently 'unpersist' -
    the production-test bug.) `files_tab` stays active->builtin (a project may override it)."""
    return os.path.join(builtin_config_project_dir(), "app_config.yaml")


def generation_params_file() -> str:
    """The relocated generation constants (user_input/generation_params.yaml; UI_REFRESH_PLAN F)."""
    return os.path.join(user_input_dir(), "generation_params.yaml")


def load_generation_params() -> dict:
    """user_input/generation_params.yaml - the ACTIVE project's copy, falling back to the BUILTIN one
    (an older project folder inherits the app's values). Raises when NEITHER exists: generation
    constants are config, never code defaults (the config-completeness rule)."""
    candidates = (generation_params_file(),
                  os.path.join(builtin_config_project_dir(), "user_input", "generation_params.yaml"))
    for path in candidates:
        if os.path.exists(path):
            return _read_yaml(path)
    raise RuntimeError("generation_params.yaml missing (looked in: " + "; ".join(candidates) + ")")


def load_files_tab():
    """The Files-tab structure: `files_tab.sections` from the ACTIVE app_config.yaml, falling back to the
    BUILTIN one (the tab structure is app-level UI - a project may override it, and an older project
    folder without the section inherits the app's). Returns None when neither defines it - the tab shows
    a pointed warning instead of a code-baked default (the config-completeness rule)."""
    for path in (app_config_file(), os.path.join(builtin_config_project_dir(), "app_config.yaml")):
        try:
            cfg = _read_yaml(path) if os.path.exists(path) else {}
        except Exception:  # noqa: BLE001 - a broken yaml falls through to the next candidate
            continue
        section = cfg.get("files_tab") if isinstance(cfg, dict) else None
        sections = section.get("sections") if isinstance(section, dict) else None
        if isinstance(sections, list):
            return sections
    return None


APP_FONT_SIZES = (10, 12, 14)             # the log-viewer Font dropdown choices
_DEFAULT_FONT_SIZE = 10


_DEFAULT_WINDOW = (1180, 720)             # GUI window fallback when app_config has no saved size


def _resolve_font_size(value) -> int:
    """Coerce a stored font-size value to one of APP_FONT_SIZES (default 10 on anything else)."""
    try:
        size = int(value)
    except (TypeError, ValueError):
        return _DEFAULT_FONT_SIZE
    return size if size in APP_FONT_SIZES else _DEFAULT_FONT_SIZE


def _resolve_theme(value) -> str:
    """Coerce a stored theme to 'light' | 'dark' (default 'dark')."""
    return "light" if str(value or "").strip().lower() == "light" else "dark"


def _resolve_dim(value, default: int) -> int:
    """Coerce a stored window dimension to a sane positive int (>= 400), else the default."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return n if n >= 400 else default


def load_app_ui() -> dict:
    """The `user_interface` block of app_config.yaml. `log_levels` -> the SET of log levels the GUI shows
    (`severity.resolve_set`: single chars or full names, first-char parsed; the PHASE banner always
    shown). `language` -> the GUI language code (`en`/`it`, default `en`). `font_size` -> the log-viewer
    font size (one of APP_FONT_SIZES, default 10). `theme` -> 'light'/'dark' (default dark). `width`/`height`
    -> the saved window size (default 1180x720). `log_to_file` -> whether the GUI tees its log to a file
    (default False). Absent file/key -> `severity.default_shown()` (all finding levels except DEBUG) + `en`
    + 10 + dark + 1180x720 + no tee. ALWAYS the BUILTIN file - UI prefs are app-scoped (see
    `builtin_app_config_file`)."""
    from pipeline4.core import severity, i18n
    path = builtin_app_config_file()
    cfg = _read_yaml(path) if os.path.exists(path) else {}
    ui = (cfg.get("user_interface") or {}) if isinstance(cfg, dict) else {}
    raw = ui.get("log_levels")
    return {"log_levels": severity.resolve_set(raw) if raw else severity.default_shown(),
            "language": i18n.normalize(ui.get("language")),
            "font_size": _resolve_font_size(ui.get("font_size")),
            "theme": _resolve_theme(ui.get("theme")),
            "width": _resolve_dim(ui.get("width"), _DEFAULT_WINDOW[0]),
            "height": _resolve_dim(ui.get("height"), _DEFAULT_WINDOW[1]),
            "log_to_file": bool(ui.get("log_to_file"))}


def _save_app_ui(**updates) -> None:
    """Set `user_interface.<key> = value` for each kwarg in the BUILTIN app_config.yaml (UI prefs are
    app-scoped - the same file load_app_ui reads, whatever project is open), round-tripping the file so
    its comments survive. The shared writer behind the simple per-key savers (`save_app_log_levels` is
    bespoke - it builds a flow-style code sequence)."""
    from ruamel.yaml import YAML
    path = builtin_app_config_file()
    yaml = YAML()                                   # round-trip mode - preserves comments
    data = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as handle:
            data = yaml.load(handle) or {}
    ui = data.get("user_interface")
    if not isinstance(ui, dict):                    # an absent OR empty (`user_interface:`) block -> {}
        ui = data["user_interface"] = {}
    ui.update(updates)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        yaml.dump(data, handle)


def save_app_font_size(size) -> None:
    """Persist the log-viewer font size (one of APP_FONT_SIZES)."""
    _save_app_ui(font_size=_resolve_font_size(size))


def save_app_language(lang: str) -> None:
    """Persist the GUI language (`en`/`it`)."""
    from pipeline4.core import i18n
    _save_app_ui(language=i18n.normalize(lang))


def save_app_theme(mode: str) -> None:
    """Persist the GUI theme (`light`/`dark`)."""
    _save_app_ui(theme=_resolve_theme(mode))


def save_app_window_size(width, height) -> None:
    """Persist the GUI window size (clamped to a sane minimum)."""
    _save_app_ui(width=_resolve_dim(width, _DEFAULT_WINDOW[0]),
                 height=_resolve_dim(height, _DEFAULT_WINDOW[1]))


def save_app_log_to_file(enabled) -> None:
    """Persist whether the GUI tees its log to a file."""
    _save_app_ui(log_to_file=bool(enabled))


def save_app_log_levels(levels) -> None:
    """Persist the GUI's shown log levels to the BUILTIN app_config.yaml `user_interface.log_levels`
    (app-scoped, like every UI pref) as first-char codes in canonical severity order (FAIL/ERROR are
    always included - they cannot be hidden). Round-trips the file so its comments survive. `levels`
    is a set/iterable of canonical level names (severity.LEVELS)."""
    from ruamel.yaml import YAML
    from ruamel.yaml.comments import CommentedSeq
    from pipeline4.core import severity
    shown = set(levels) | severity.UNHIDEABLE
    codes = CommentedSeq(level[0] for level in severity.LEVELS if level in shown)
    codes.fa.set_flow_style()                       # keep the [F, E, W, ...] one-line form
    path = builtin_app_config_file()
    yaml = YAML()                                   # round-trip mode - preserves comments
    data = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as handle:
            data = yaml.load(handle) or {}
    ui = data.get("user_interface")
    if not isinstance(ui, dict):                    # an absent OR empty (`user_interface:`) block -> {}
        ui = data["user_interface"] = {}
    ui["log_levels"] = codes
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        yaml.dump(data, handle)


# The four input-document paths the Documents tab edits (in project_params.yaml).
DOCUMENT_KEYS = ("iolist_path", "iolist_previous_path", "matrix_path", "matrix_previous_path")


def load_document_paths() -> dict:
    """The 4 input-document paths as STORED (raw, unresolved) in the active project_params.yaml - the
    Documents-tab picker shows these. A missing file/key -> ''."""
    path = params_file()
    data = _read_yaml(path) if os.path.exists(path) else {}
    if not isinstance(data, dict):
        data = {}
    return {key: str(data.get(key) or "") for key in DOCUMENT_KEYS}


def save_document_path(key: str, value) -> None:
    """Set ONE input-document path in the active project_params.yaml (round-tripping comments). A blank
    `value` clears it (stored as ''). An unknown key is a no-op."""
    if key not in DOCUMENT_KEYS:
        return
    from ruamel.yaml import YAML
    path = params_file()
    yaml = YAML()                                   # round-trip mode - preserves comments
    data = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as handle:
            data = yaml.load(handle) or {}
    data[key] = str(value or "")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        yaml.dump(data, handle)


def load_params(path: str | None = None) -> dict:
    """Load the project params (the nested schema: iolist_params / matrix_params / validation_params /
    output). The four document paths (iolist/matrix + their *_previous - the latter reserved for the
    future ph100 change-tracing) are resolved relative to the params file's directory. The output /
    device_types_db / interface_template defaults are applied by their consumers as the phases port."""
    path = path or params_file()
    params = _read_yaml(path)
    base = os.path.dirname(os.path.abspath(path))
    for key in ("iolist_path", "iolist_previous_path", "matrix_path", "matrix_previous_path"):
        if params.get(key):
            params[key] = _resolve_path(base, params[key])
    return params


def get_param(params: dict, dotted_key: str, default=None):
    """Safe nested access into the params tree. `get_param(params,
    'validation_params.crosscheck.iol_in_matrix.mandatory_words', [])` returns the value, or `default`
    when any level along the dotted path is missing or None. A present falsy value (False/0/[]) is
    returned as-is, NOT replaced by the default."""
    node = params
    for part in dotted_key.split("."):
        if not isinstance(node, dict) or node.get(part) is None:
            return default
        node = node[part]
    return node


# --- config CSVs (read via core.table's JSON-cell codec; tolerant of hand edits) ----------------- #
def input_docs_dir() -> str:
    return os.path.join(config_project_dir(), "input_docs")


def _as_bool(value, default: bool = False) -> bool:
    text = str(value if value is not None else "").strip().lower()
    if text in ("true", "yes", "y", "1", "on"):
        return True
    if text in ("false", "no", "n", "0", "off", ""):
        return False
    return default


def read_config_csv(path: str, json_columns=()) -> list:
    """Read a config CSV to a list of dict rows. The declared `json_columns` are JSON-decoded with the
    SAME codec as the SSOT tables (`core.table.decode_cell`), so a `|`-free list/object cell round-trips;
    every other column stays a string. Blank rows are skipped (config files are hand-edited). Missing
    file -> []."""
    from pipeline4.core.table import decode_cell
    if not os.path.exists(path):
        return []
    wanted = set(json_columns)
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as handle:
        for raw in csv.DictReader(handle):
            if not any((v or "").strip() for v in raw.values() if isinstance(v, str)):
                continue
            rows.append({key: (decode_cell(value) if key in wanted else value)
                         for key, value in raw.items()})
    return rows


def load_column_map(document: str) -> list:
    """Column-map rows for one document (IoList / CE): {column, canonical, expected_header, required,
    preliminary_check_exclude}. `preliminary_check_exclude` marks the pipeline-written columns (AA-AG)
    that the phase-100 standalone validation ignores."""
    return [{
        "column": (r.get("column") or "").strip(),
        "canonical": (r.get("canonical") or "").strip(),
        "expected_header": (r.get("expected_header") or "").strip(),
        "required": _as_bool(r.get("required")),
        "preliminary_check_exclude": _as_bool(r.get("preliminary_check_exclude")),
    } for r in read_config_csv(os.path.join(input_docs_dir(), "column_map.csv"))
        if (r.get("document") or "").strip() == document]


def load_change_weights() -> dict:
    """The ph100 before/after report weight model (`change_weights.csv`): {document -> {field -> tier}},
    tier in {critical, major, minor, exclude, effect}. `exclude` drops the column from the comparison
    entirely (a dead/never-authored column); `effect` marks a C&E effect column (X/blank, handled
    specially - a lost effect is a regression, a new one an upgrade roll-out). A present field absent from
    the file defaults to `minor` at compare time. Missing file -> {} (everything defaults to minor)."""
    out: dict = {}
    for r in read_config_csv(os.path.join(input_docs_dir(), "change_weights.csv")):
        document = (r.get("document") or "").strip()
        field = (r.get("field") or "").strip()
        if not document or not field:
            continue
        out.setdefault(document, {})[field] = (r.get("tier") or "minor").strip().lower() or "minor"
    return out


def _load_rules(filename: str) -> list:
    """Load a priority-ordered ruleset CSV (ph200 classification): rows of {priority, when, type/gate, ...}
    sorted ascending by `priority` (first-match-wins). Cells stay raw strings - the `when`/`type` cells are
    expressions evaluated by `core.expr`. Missing file -> []."""
    rows = read_config_csv(os.path.join(input_docs_dir(), filename))
    rows.sort(key=lambda r: int((r.get("priority") or "0").strip() or 0))
    return rows


def load_gate_rules() -> list:
    """The In/Out/Node gate ruleset (`gate_rules.csv`): rows {priority, when, gate} - first match sets the
    row's gate (the ph200 §6 classification partitions by it)."""
    return _load_rules("gate_rules.csv")


def load_script_type_rules() -> list:
    """The script-type classification ruleset (`script_type_rules.csv`): rows {priority, gate, when, type} -
    first matching rule (within the row's gate, or `any`) yields the script_type (ph200 §6 / sub-phase 210)."""
    return _load_rules("script_type_rules.csv")


def load_signal_types() -> dict:
    """type_id (upper) -> the type record (the stripped PL4 schema: identity + tag + ce_mandatory; the
    DB / diagnosis / interface attributes now live in their own registries). A paired channel-2 type
    inherits the sibling's tagtable_name (linked by pair_key)."""
    types = {}
    for r in read_config_csv(os.path.join(input_docs_dir(), "signal_types.csv")):
        tid = (r.get("type_id") or "").strip()
        if not tid:
            continue
        types[tid.upper()] = {
            "type_id": tid,
            "type_id_desc": (r.get("type_id_desc") or "").strip(),
            "category": (r.get("category") or "").strip(),
            "pair_key": (r.get("pair_key") or "").strip(),
            "channel": (r.get("channel") or "").strip(),
            "is_pattern": _as_bool(r.get("is_pattern")),
            "tagtable_name": (r.get("tagtable_name") or "").strip(),
            "tag_name": (r.get("tag_name") or "").strip(),
            "io_comment": (r.get("io_comment") or "").strip(),
            "ce_mandatory": (r.get("ce_mandatory") or "").strip().lower(),
        }
    inherited = {}
    for t in types.values():
        if t["pair_key"] and t["tagtable_name"]:
            inherited.setdefault(t["pair_key"], t["tagtable_name"])
    for t in types.values():
        if not t["tagtable_name"] and t["pair_key"] in inherited:
            t["tagtable_name"] = inherited[t["pair_key"]]
    return types


def resolve_type(types: dict, raw_type) -> dict | None:
    """Resolve a raw script-type cell to a signal_types record, honoring pattern types (`Z#` matches
    Z1, Z2, ...). Returns None when unknown/blank."""
    clean = str(raw_type if raw_type is not None else "").strip()
    if not clean:
        return None
    exact = types.get(clean.upper())
    if exact:
        return exact
    for record in types.values():
        if not record["is_pattern"]:
            continue
        prefix = record["type_id"].split("#")[0].upper()
        rest = clean.upper()[len(prefix):] if clean.upper().startswith(prefix) else ""
        if rest and rest.isdigit():
            return record
    return None


# Phase 400 interface mirroring: free bytes between the template's last used I/O Offset Byte and the start
# of the mirrored "custom data" block (per direction).
INTERFACE_CUSTOM_GAP = 8


# --- phase-400 chain-reactions CSVs (chain_reactions/) ------------------------------------------- #
def chain_reactions_dir() -> str:
    """The phase-400 chain-reaction CSVs (object_families / interface_elements / interface_tagnames)."""
    return os.path.join(config_project_dir(), "chain_reactions")


def diagnosis_dir() -> str:
    """The diagnosis config CSVs (diagnosis_columns / diagnosis_logic_rules)."""
    return os.path.join(config_project_dir(), "diagnosis")


def _split_required_types(value) -> list:
    return [t.strip() for t in str(value or "").split("|") if t.strip()]


def load_diagnosis_logic_rules() -> list:
    """The trigger-driven follower rules (phase 400 mirroring + phase 610). Columns: name, required_types
    ('|'-OR trigger script_types), dev_type, db_name, member (a `{canonical}` template), interface_tagname,
    diag_desc. A rule fires once per row whose script_type is ANY of `required_types`."""
    out = []
    for r in read_config_csv(os.path.join(diagnosis_dir(), "diagnosis_logic_rules.csv")):
        if not (r.get("name") or "").strip():
            continue
        out.append({
            "name": (r.get("name") or "").strip(),
            "required_types": _split_required_types(r.get("required_types")),
            "dev_type": (r.get("dev_type") or "").strip(),
            "db_name": (r.get("db_name") or "").strip(),
            "member": (r.get("member") or "").strip(),
            "interface_tagname": (r.get("interface_tagname") or "").strip(),
            "diag_desc": (r.get("diag_desc") or "").strip(),
        })
    return out


def load_signal_diagnosis() -> dict:
    """type_id (upper) -> {in_diag:bool, diag_logic, diag_desc(template), tristate:bool, tristate_desc}.
    The per-type diagnosis attributes relocated from PL3's `signal_types.csv` (cols in_diag/diag_logic/
    diag_desc/tristate_desc), PLUS a new explicit per-type `tristate` enable flag (the user's addition).
    Merged onto the staged `type` object (in_diag/diag_logic/tristate/tristate_desc) + resolved onto the
    row (`diag_desc`). A type absent from the CSV defaults to in_diag=False (not a diagnosis signal)."""
    out = {}
    for r in read_config_csv(os.path.join(diagnosis_dir(), "signal_diagnosis.csv")):
        tid = (r.get("type_id") or "").strip()
        if not tid:
            continue
        out[tid.upper()] = {
            "in_diag": _as_bool(r.get("in_diag")),
            "diag_logic": (r.get("diag_logic") or "").strip(),
            "diag_desc": (r.get("diag_desc") or "").strip(),
            "tristate": _as_bool(r.get("tristate")),
            "tristate_desc": (r.get("tristate_desc") or "").strip(),
        }
    return out


def load_diagnosis_columns() -> list:
    """The DiagList column model (phase 610): [{header, expression}] in order, where each expression is a
    `{canonical}` template (the one sentinel `$PLC_Binding$` resolves to the signal's plc_binding). Drives
    BOTH DiagList_IO.csv and DiagList_Logic.csv."""
    return [{"header": (r.get("header") or "").strip(), "expression": (r.get("expression") or "")}
            for r in read_config_csv(os.path.join(diagnosis_dir(), "diagnosis_columns.csv"))
            if (r.get("header") or "").strip()]


def parse_params_by_type(blob: str) -> dict:
    """'<B1/2>p=1 | q=0<B1/2><DI1/2>r=0<DI1/2>' -> {'B1/2': 'p=1 | q=0', 'DI1/2': 'r=0'} (DTD col-6, the
    per-signal-type module parameter blocks; phase 700)."""
    out = {}
    for st, block in re.findall(r"<([^>]+)>(.*?)<\1>", blob or ""):
        out[st.strip().upper()] = block.strip()
    return out


def load_device_types_db(params: dict | None = None) -> dict:
    """The global DeviceTypesDatabase (phase 700; delim-sniffed, manually maintained). Returns
    {by_id: {ID_upper -> rec}, default_cards: {parent_upper -> [card_id, ...]}}. A `<PARENT>:SUFFIX`
    identifier is a default card of PARENT. Columns: model_id, dev_type, order, comment, params (col-5,
    Open2App-applied - NEVER written), params_by_type (col-6), io_addr_params (col-7)."""
    path = (params or {}).get("device_types_db") or DEVICE_TYPES_DB_DEFAULT
    by_id, default_cards = {}, {}
    with open(path, encoding="utf-8-sig") as f:
        text = f.read()
    first = next((ln for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")), "")
    delim = ";" if first.count(";") > first.count(",") else ","
    for c in csv.reader(text.splitlines(), delimiter=delim):
        if not c or not c[0].strip() or c[0].lstrip().startswith("#"):
            continue
        ident = c[0].strip()
        rec = {
            "model_id": ident,
            "dev_type": c[1].strip() if len(c) > 1 else "",
            "order": c[2].strip() if len(c) > 2 else "",
            "comment": c[3].strip() if len(c) > 3 else "",
            "params": c[4].strip() if len(c) > 4 else "",
            "params_by_type": parse_params_by_type(c[5] if len(c) > 5 else ""),
            "io_addr_params": c[6].strip() if len(c) > 6 else "",
            "parent": None,
        }
        m = re.match(r"^<(.+?)>:(.+)$", ident)
        if m:
            rec["parent"] = m.group(1).strip()
            default_cards.setdefault(m.group(1).strip().upper(), []).append(ident)
        by_id[ident.upper()] = rec
    return {"by_id": by_id, "default_cards": default_cards}


def load_interface_elements() -> list:
    """The interface-element follower rules (phase 400): a mirrored signal of a matching script_type spawns
    an extra coupler element. Columns: name, required_types ('|'-OR), dev_type, direction (I/Q - the ONLY
    source that may add an INPUT row), data_type (BOOL/WORD), script_type (byte-grouping label; defaults to
    name), member (mirror-name `{canonical}` template), interface_tagname."""
    out = []
    for r in read_config_csv(os.path.join(chain_reactions_dir(), "interface_elements.csv")):
        if not (r.get("name") or "").strip():
            continue
        out.append({
            "name": (r.get("name") or "").strip(),
            "required_types": _split_required_types(r.get("required_types")),
            "dev_type": (r.get("dev_type") or "").strip(),
            "direction": "I" if (r.get("direction") or "").strip().upper() == "I" else "Q",
            "data_type": "WORD" if (r.get("data_type") or "").strip().upper() == "WORD" else "BOOL",
            "script_type": (r.get("script_type") or "").strip() or (r.get("name") or "").strip(),
            "member": (r.get("member") or "").strip(),
            "interface_tagname": (r.get("interface_tagname") or "").strip(),
        })
    return out


def load_tagtable_elements() -> list:
    """The EXTRA-tag rules (phase 510, `chain_reactions/tagtable_elements.csv`) - the datablock_elements
    logic aimed at TAG TABLES (user spec 2026-07-07): per for_each match, one additional PLC tag in
    `tag_table`. `name` / `io_address` / `comment` are FULL expression templates over the matched row
    ({expr} holes - io_address is where the engine earns its keep, e.g.
    `{regex_replace($bit, /^I/, 'Q')}`); `datatype` defaults to Bool. Missing file -> [] (no extra tags)."""
    out = []
    for r in read_config_csv(os.path.join(chain_reactions_dir(), "tagtable_elements.csv")):
        if not (r.get("tag_table") or "").strip():
            continue
        out.append({
            "tag_table": (r.get("tag_table") or "").strip(),
            "name": (r.get("name") or "").strip(),
            "for_each": (r.get("for_each") or "").strip(),
            "datatype": (r.get("datatype") or "").strip() or "Bool",
            "io_address": (r.get("io_address") or "").strip(),
            "comment": (r.get("comment") or "").strip(),
        })
    return out


def load_interface_tagnames() -> dict:
    """type_id (upper) -> the interface_tagname template (Signal Name Side 1 base), relocated from PL3's
    `signal_types.csv` col 18. Keeps `{interface_name}`/`{interface_id}` for the phase-400 generator; in
    PL4 `{tag_name}`/`{db_element}` resolve to the staged `name_in_tagtable` / 520 `name_in_db`."""
    out = {}
    for r in read_config_csv(os.path.join(chain_reactions_dir(), "interface_tagnames.csv")):
        tid = (r.get("type_id") or "").strip()
        if tid:
            out[tid.upper()] = (r.get("interface_tagname") or "").strip()
    return out


# --- phase-520 data-block registry CSVs (datablocks/) -------------------------------------------- #
def datablocks_dir() -> str:
    """The phase-520 data-block registry CSVs (datablock_definitions / _elements / _types)."""
    return os.path.join(config_project_dir(), "datablocks")


def _bool_default(value, default: bool) -> bool:
    """`_as_bool`, but a BLANK cell falls back to `default` (the DB-config bool columns; PL3's `_b`).
    PL4's `_as_bool` reads a blank as False, so the DB loaders need this to honor a column's real default."""
    text = str(value if value is not None else "").strip()
    return _as_bool(text) if text else default


def load_db_definitions() -> list:
    """The AUTHORITATIVE DB registry (phase 520): every data block, Global or an Instance family. Columns:
    db_name (literal, or a PEP-3101 template for a family), db_type (Global|Instance), db_programming_language
    (DB|F_DB), instance_of (the FB, for an Instance), for_each (the iteration DSL), memory_layout
    (Optimized|Standard), opc_ua/webserver/only_load_memory/write_protected/retain_reserve (bool),
    memory_reserve, seed (bool), create_when (always|if_elements|never), comment. Missing file -> []."""
    out = []
    for r in read_config_csv(os.path.join(datablocks_dir(), "datablock_definitions.csv")):
        if not (r.get("db_name") or "").strip():
            continue
        pl = (r.get("db_programming_language") or "DB").strip() or "DB"
        out.append({
            "db_name": (r.get("db_name") or "").strip(),
            "db_type": (r.get("db_type") or "Global").strip() or "Global",
            "db_programming_language": pl,
            "instance_of": (r.get("instance_of") or "").strip(),
            "for_each": (r.get("for_each") or "").strip(),
            "memory_layout": (r.get("memory_layout") or "Optimized").strip() or "Optimized",
            "opc_ua": _bool_default(r.get("opc_ua"), pl.upper() != "F_DB"),  # blank defaults OFF for a fail-safe DB
            "webserver": _bool_default(r.get("webserver"), True),
            "only_load_memory": _bool_default(r.get("only_load_memory"), False),
            "write_protected": _bool_default(r.get("write_protected"), False),
            "retain_reserve": _bool_default(r.get("retain_reserve"), False),
            "memory_reserve": (r.get("memory_reserve") or "").strip(),
            "seed": _bool_default(r.get("seed"), False),
            "create_when": (r.get("create_when") or "if_elements").strip().lower() or "if_elements",
            "comment": (r.get("comment") or "").strip(),
        })
    return out


def load_db_elements() -> list:
    """The Global-DB members (phase 520). Columns: db_name, member (PEP-3101 template), for_each (the
    iteration DSL), datatype, start_value, retain (bool), ext_accessible/ext_visible/ext_writable (bool),
    setpoint (bool), comment. Missing file -> []."""
    out = []
    for r in read_config_csv(os.path.join(datablocks_dir(), "datablock_elements.csv")):
        if not (r.get("db_name") or "").strip():
            continue
        out.append({
            "db_name": (r.get("db_name") or "").strip(),
            "member": (r.get("member") or "").strip(),
            "for_each": (r.get("for_each") or "").strip(),
            "datatype": (r.get("datatype") or "").strip() or "Bool",
            "start_value": (r.get("start_value") or "").strip(),
            "retain": _bool_default(r.get("retain"), False),
            "ext_accessible": _bool_default(r.get("ext_accessible"), True),
            "ext_visible": _bool_default(r.get("ext_visible"), True),
            "ext_writable": _bool_default(r.get("ext_writable"), True),
            "setpoint": _bool_default(r.get("setpoint"), False),
            "comment": (r.get("comment") or "").strip(),
        })
    return out


def load_db_types() -> list:
    """The valid member data types (phase 520 validation). Columns: name, kind (Elementary|UDT), comment.
    Missing file -> []."""
    out = []
    for r in read_config_csv(os.path.join(datablocks_dir(), "datablock_types.csv")):
        if not (r.get("name") or "").strip():
            continue
        out.append({"name": (r.get("name") or "").strip(),
                    "kind": (r.get("kind") or "Elementary").strip() or "Elementary",
                    "comment": (r.get("comment") or "").strip()})
    return out
