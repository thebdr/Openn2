"""YAML-backed parameters: project_params.yaml, the app-UI prefs (app_config.yaml), and the
sheet-pattern resolution their values use.

Three families live here: (1) `load_params`/`get_param` - the nested project params + the safe dotted
accessor; (2) `load_app_ui` + the `save_app_*` writers - the APP-scoped UI preferences (always the
BUILTIN app_config.yaml; round-tripped so comments survive) and the Documents-tab path load/save;
(3) `resolve_sheet(s)` - matching the params' JS-style sheet regexes against a workbook.
"""
from __future__ import annotations

import os
import re

from pipeline5.config.paths import (
    builtin_config_project_dir,
    config_project_dir,
    user_input_dir,
)


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
    """The active project params file - the SHARED tier's project_params.yaml (the open project's,
    else the app's builtin)."""
    return os.path.join(config_project_dir(), "shared", "project_params.yaml")


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


def generation_params_file():
    """The generation constants - a SYSTEM-tier file since the step-4 regroup, resolved through the
    4-tier walk (project-system -> project-shared -> system-builtin -> builtin-shared)."""
    from pipeline5.config.resolver import find
    return find("generation_params.yaml")


def load_generation_params() -> dict:
    """generation_params.yaml through the resolver. Raises when NO tier holds it: generation
    constants are config, never code defaults (the config-completeness rule)."""
    path = generation_params_file()
    if path:
        return _read_yaml(path)
    from pipeline5.config.resolver import tiers
    raise RuntimeError("generation_params.yaml missing (looked in: " + "; ".join(tiers()) + ")")


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
    from pipeline5.findings import severity
    from pipeline5.language import i18n
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
    from pipeline5.language import i18n
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
    from pipeline5.findings import severity
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
