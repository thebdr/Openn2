"""PL4 configuration: paths, project isolation, and sheet-name resolution.

The CSV / JSON-cell loaders are added here as the phases that need them are ported. The top-level
**Database/** folder (the SSOT - DESIGN 10.3) and the **Output/** tree (the OPn `BuilderData/` export
surface) both follow the active project (`use_project`) or default to `Shared/` (the builtin), so the
whole app is project-isolated with no special-casing downstream.
"""
from __future__ import annotations

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
_BUILTIN_CONFIG_PROJECT = os.path.join(APP_ROOT, "config_project")
_BUILTIN_DATABASE = os.path.join(SHARED, "Database")        # the SSOT folder (DESIGN 10.3)
_BUILTIN_OUTPUT = os.path.join(SHARED, "OutputTree")        # the OPn BuilderData export surface

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


def database_dir() -> str:
    """The top-level Database/ folder - the SSOT (one CSV-with-JSON-cells per table)."""
    return os.path.join(_PROJECT_ROOT, "Database") if _PROJECT_ROOT else _BUILTIN_DATABASE


def output_root() -> str:
    """The BuilderData/ export root - what OPn imports."""
    return os.path.join(_PROJECT_ROOT, "Output") if _PROJECT_ROOT else _BUILTIN_OUTPUT


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
