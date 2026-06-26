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
