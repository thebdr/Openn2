"""Loads the versioned config (CSV tables + project_params.yaml) and resolves the _Openn2 layout.

Layout (this module sits at Pipeline3App/pipeline3/core/config.py):
  Pipeline3App/                       <- APP_ROOT
    config_project/                   <- per-project config (CONFIG_PROJECT)
      project_params.yaml             <- PARAMS_FILE
      designer_params.yaml            <- DESIGNER_PARAMS_FILE (validation-only base)
      input_docs/  *.csv              <- column_map, signal_types, iolist_columns,
                                         iolist_permanent_parts, object_families, datablock_elements_rules
      diagnosis/   *.csv              <- diagnosis_columns, diagnosis_logic_rules
      block_templates.json            <- BLOCK_TEMPLATES_JSON
    user_input/  error_management.csv <- USER_INPUT (treatments, persist between runs)
  ../Shared/                          <- SHARED (the handoff with Open2App)
    Templates/                        <- TEMPLATES_DIR (TIA software blocks + machine interfaces)
    HardwareConfigBuilderData/DeviceTypesDatabase.csv
    OutputTree/                       <- OUTPUT_ROOT (every generated artifact)

Open2App import surface (plan §10, CONFIRMED): Open2App imports ONLY from
  Shared/OutputTree/TiaPortalProjectInterface/BuilderData/  (hardware_dir, blocks_creation_dir,
  blocks_import_dir, io_tags_dir). The ProjectDocumentation/* and Reports/* trees are
  documentation/intermediate and are NOT imported - so OUTPUT_PATHS for the BuilderData keys must
  stay byte-stable.
"""
from __future__ import annotations
import csv
import json
import os
import sys

# APP_ROOT = the Pipeline3App dir (dev: this file's great-grandparent; frozen: the bundle/exe dir).
if getattr(sys, "frozen", False):
    APP_ROOT = getattr(sys, "_MEIPASS", None) or os.path.dirname(sys.executable)
else:
    # pipeline3/core/config.py -> core -> pipeline3 -> Pipeline3App
    APP_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_PROJECT = os.path.join(APP_ROOT, "config_project")
INPUT_DOCS_DIR = os.path.join(CONFIG_PROJECT, "input_docs")
DIAGNOSIS_DIR = os.path.join(CONFIG_PROJECT, "diagnosis")
USER_INPUT = os.path.join(APP_ROOT, "user_input")
SHARED = os.path.normpath(os.path.join(APP_ROOT, os.pardir, "Shared"))
TEMPLATES_DIR = os.path.join(SHARED, "Templates")
BLOCK_TEMPLATES_DIR = os.path.join(TEMPLATES_DIR, "Tia Portal Software Blocks")
OUTPUT_ROOT = os.path.join(SHARED, "OutputTree")
PARAMS_FILE = os.path.join(CONFIG_PROJECT, "project_params.yaml")
DESIGNER_PARAMS_FILE = os.path.join(CONFIG_PROJECT, "designer_params.yaml")
APP_CONFIG_FILE = os.path.join(CONFIG_PROJECT, "app_config.yaml")   # picks the launch profile (main|designer|…)
BLOCK_TEMPLATES_JSON = os.path.join(CONFIG_PROJECT, "block_templates.json")
CONFIG_DIR = CONFIG_PROJECT                # alias: "open the config folder"

# The ACTIVE project's root (None = the builtin app config). The GUI calls use_project() on project
# open/close so the CSV loaders + the treatment registry read the project's OWN config_project/ +
# user_input/ (per-project isolation). None keeps the app defaults - and so the default output
# Shared/OutputTree, which is the Open2App/Openn3 import contract.
_PROJECT_ROOT: str | None = None


def use_project(root: str | None) -> None:
    """Point the config-CSV loaders + the treatment registry at <root>/config_project + <root>/user_input.
    `None` reverts to the builtin app config (config_project/ + user_input/)."""
    global _PROJECT_ROOT
    _PROJECT_ROOT = root or None


def use_builtin() -> None:
    """Revert to the builtin app config (no project)."""
    use_project(None)


def active_project() -> str | None:
    return _PROJECT_ROOT


def config_project_dir() -> str:
    return os.path.join(_PROJECT_ROOT, "config_project") if _PROJECT_ROOT else CONFIG_PROJECT


def input_docs_dir() -> str:
    return os.path.join(config_project_dir(), "input_docs")


def diagnosis_dir() -> str:
    return os.path.join(config_project_dir(), "diagnosis")


def datablocks_dir() -> str:
    """The phase-520 data-block registry CSVs (datablock_definitions/_elements/_types)."""
    return os.path.join(config_project_dir(), "datablocks")


def user_input_dir() -> str:
    return os.path.join(_PROJECT_ROOT, "user_input") if _PROJECT_ROOT else USER_INPUT

# Where New / Save As create a project (a self-contained <PROJECTS_DIR>/<name> directory). The
# default is overridable by the PIPELINE3_PROJECTS env var AND, at runtime, user-selectable
# (persisted by the GUI) - see plan §4 Project Manager.
PROJECTS_DIR = os.environ.get("PIPELINE3_PROJECTS") or os.path.join(os.path.expanduser("~"), "Pipeline3 Projects")

# Shared-data defaults (used when project_params.yaml omits / can't resolve them):
DEVICE_TYPES_DB_DEFAULT = os.path.join(SHARED, "HardwareConfigBuilderData", "DeviceTypesDatabase.csv")
INTERFACE_TEMPLATE_DEFAULT = os.path.join(TEMPLATES_DIR, "MachineInterfaces", "TEMPLATE_INTERFACES_v0.0.xlsx")

# Phase 400 interface mirroring: free bytes left between the template's last used I/O Offset Byte and
# the start of the mirrored "custom data" block (per direction).
INTERFACE_CUSTOM_GAP = 8

# Generated outputs land under the run's output root (default OUTPUT_ROOT = Shared/OutputTree) at
# these semantic subpaths. The BuilderData/* keys are the Open2App import contract (keep stable).
OUTPUT_PATHS = {
    # --- documentation / intermediate (NOT imported by Open2App) --- #
    "validation_report":   os.path.join("Reports", "documents_validation_report"),     # + .txt / .html (complete log)
    "validation_errors":   os.path.join("Reports", "documents_validation_errors"),      # + .txt / .html (errors-only view)
    "coverage_report":     os.path.join("Reports", "io_project_coverage_report"),       # + .csv / .txt
    "run_log":             os.path.join("Reports", "pipeline_run_log"),                 # + .txt (GUI "Log to File" tee)
    "io_database":         os.path.join("ProjectDocumentation", "InformationDatabase", "IODatabase.csv"),
    "diagnosis_dir":       os.path.join("ProjectDocumentation", "InformationDatabase", "DiagnosisData"),
    "interfaces_dir":      os.path.join("ProjectDocumentation", "InformationDatabase", "Interfaces"),
    "populated_iolist":    os.path.join("ProjectDocumentation", "InformationDatabase", "PopulatedIoList"),
    # --- the Open2App import surface (Shared/OutputTree/TiaPortalProjectInterface/BuilderData) --- #
    "hardware_dir":        os.path.join("TiaPortalProjectInterface", "BuilderData", "HardwareConfiguration"),
    "blocks_creation_dir": os.path.join("TiaPortalProjectInterface", "BuilderData", "SoftwareBlocks", "CreationInfo"),
    "blocks_import_dir":   os.path.join("TiaPortalProjectInterface", "BuilderData", "SoftwareBlocks", "ImportReady"),
    "io_tags_dir":         os.path.join("TiaPortalProjectInterface", "BuilderData", "PlcTags"),
}

# The subset of OUTPUT_PATHS that Open2App imports (the contract test asserts exactly these).
OPEN2APP_KEYS = ("hardware_dir", "blocks_creation_dir", "blocks_import_dir", "io_tags_dir")


def output_root(params: dict | None = None) -> str:
    """Root of the generated-artifact tree. Default = OUTPUT_ROOT (Shared/OutputTree); an absolute
    params['output_dir'] overrides it (a project's load_params resolves output_dir: Output to an
    absolute <project>/Output, so an open project writes into itself)."""
    d = (params or {}).get("output_dir")
    return d if (d and os.path.isabs(d)) else OUTPUT_ROOT


def out_path(out_root: str, key: str, *extra) -> str:
    """A generated-output path: <out_root>/<OUTPUT_PATHS[key]>[/<extra...>]."""
    return os.path.join(out_root, OUTPUT_PATHS[key], *extra)


_TRUE = {"yes", "true", "1", "y"}


def as_bool(value) -> bool:
    return str(value).strip().lower() in _TRUE


def as_sheet_list(value) -> list:
    """A 'sheet' / 'matrix_sheet' value (single name or list) -> list of pattern strings
    (each a regex; see resolve_sheets)."""
    if isinstance(value, (list, tuple)):
        return [str(s).strip() for s in value if str(s).strip()]
    s = str(value or "").strip()
    return [s] if s else []


def _sniff_delim(text: str) -> str:
    """',' unless the first non-empty, non-comment line clearly uses ';' more (transition-safe)."""
    first = next((ln for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")), "")
    return ";" if first.count(";") > first.count(",") else ","


def _read_csv(name: str, base: str | None = None) -> list:
    path = os.path.join(base or input_docs_dir(), name)
    with open(path, newline="", encoding="utf-8-sig") as f:
        text = f.read()
    return list(csv.DictReader(text.splitlines(), delimiter=_sniff_delim(text)))


def js_to_re(pattern: str) -> str:
    """Accept a JS-style regex literal - '/pattern/flags' or 'pattern/flags' (g/m/i/...) - and
    return the bare Python pattern (flags stripped; matching is case-insensitive anyway). A plain
    pattern or a literal sheet name is returned unchanged. Backslash regexes must be SINGLE-quoted
    in YAML (double quotes treat '\\d' as an invalid escape)."""
    import re
    s = str(pattern or "").strip()
    m = re.match(r"^/?(.*)/([gimsuxy]+)$", s)        # only strip when real trailing flag letters
    if m:
        return m.group(1)
    if len(s) >= 2 and s.startswith("/") and s.endswith("/"):   # bare /pattern/ wrapper, no flags
        return s[1:-1]
    return s


def resolve_sheets(patterns, available) -> list:
    """Match sheet-name `patterns` (each a regex, case-insensitive re.search; JS '/.../flags'
    literals accepted; an invalid regex falls back to an exact case-insensitive name match) against
    the workbook's `available` sheet names. Returns matching names in workbook order, de-duplicated."""
    import re
    compiled = []
    for p in as_sheet_list(patterns):
        pat = js_to_re(p)
        try:
            compiled.append(("re", re.compile(pat, re.IGNORECASE)))
        except re.error:
            compiled.append(("lit", pat.lower()))
    out = []
    for name in available:
        for kind, p in compiled:
            if (p.search(name) if kind == "re" else p == name.lower()):
                out.append(name)
                break
    return out


def resolve_sheet(pattern, available) -> str | None:
    """The first sheet name matching `pattern`, or None (single-sheet contexts e.g. the C&E matrix)."""
    m = resolve_sheets(pattern, available)
    return m[0] if m else None


def _read_params_file(path: str) -> dict:
    if path.lower().endswith((".yaml", ".yml")):
        from ruamel.yaml import YAML
        with open(path, encoding="utf-8") as f:
            return dict(YAML(typ="safe").load(f) or {})
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _resolve_doc(base: str, rel: str) -> str:
    return os.path.normpath(os.path.join(base, rel))


def load_params(path: str | None = None) -> dict:
    """Load a params file. Resolves io_list/ce paths relative to the params file's directory; a
    project's own params file defaults output_dir to 'Output' (resolved to absolute); device_types_db
    / interface_template fall back to the Shared defaults when absent/unresolvable."""
    path = path or PARAMS_FILE
    params = _read_params_file(path)
    base = os.path.dirname(os.path.abspath(path))
    for key in ("io_list", "ce"):
        if key in params and params[key].get("path") and not os.path.isabs(params[key]["path"]):
            params[key] = dict(params[key], path=_resolve_doc(base, params[key]["path"]))
    _builtin = {os.path.abspath(PARAMS_FILE), os.path.abspath(DESIGNER_PARAMS_FILE)}
    if os.path.abspath(path) not in _builtin and not str(params.get("output_dir") or "").strip():
        params["output_dir"] = "Output"
    if params.get("output_dir") and not os.path.isabs(params["output_dir"]):
        params["output_dir"] = _resolve_doc(base, params["output_dir"])
    for key, dflt in (("device_types_db", DEVICE_TYPES_DB_DEFAULT),
                      ("interface_template", INTERFACE_TEMPLATE_DEFAULT)):
        val = params.get(key)
        if not val:
            params[key] = dflt
        elif not os.path.isabs(val):
            cand = _resolve_doc(base, val)
            params[key] = cand if os.path.exists(cand) else dflt
    return params


# UI launch settings (start values - the window stays resizable; the theme/log toggles still work).
# The defaults reproduce today's look, so a missing app_config.yaml / user_interface block = current.
APP_UI_DEFAULTS = {"width": 1180, "height": 760, "theme": "dark", "log_to_file": False}


def load_app_config() -> dict:
    """The full config_project/app_config.yaml mapping (profile + user_interface …); {} on any error
    (missing / malformed) so callers can read it without guarding."""
    try:
        return _read_params_file(APP_CONFIG_FILE) or {}
    except Exception:  # noqa: BLE001  (no file / malformed -> safe default)
        return {}


def load_app_profile() -> str:
    """The launch profile from app_config.yaml (`profile: <name>`), lowercased. Missing / blank /
    unreadable -> 'main'. NOT validated here (the GUI checks it against the REGISTERED profiles), so
    adding a future profile needs no change to this loader."""
    return str(load_app_config().get("profile") or "").strip().lower() or "main"


def load_app_ui() -> dict:
    """The `user_interface` launch block, merged over APP_UI_DEFAULTS and validated: width/height ->
    positive int else default (START size only - the window stays resizable); theme -> 'dark'|'light'
    else default; log_to_file -> bool (only when the key is present). Unknown keys are ignored, so a
    new setting can be added to app_config.yaml without breaking an older build."""
    ui = dict(APP_UI_DEFAULTS)
    raw = load_app_config().get("user_interface")
    if isinstance(raw, dict):
        for k in ("width", "height"):
            try:
                v = int(raw.get(k))
            except (TypeError, ValueError):
                continue
            if v > 0:
                ui[k] = v
        theme = str(raw.get("theme") or "").strip().lower()
        if theme in ("dark", "light"):
            ui["theme"] = theme
        if "log_to_file" in raw:
            ui["log_to_file"] = as_bool(raw.get("log_to_file"))
    return ui


def profile_params_file(profile: str | None) -> str:
    """The builtin params base for a profile (= no project open): project_params.yaml for 'main',
    else config_project/<profile>_params.yaml. So 'designer' -> the existing designer_params.yaml and
    a future 'foo' -> foo_params.yaml, by convention, with no code change."""
    if not profile or profile == "main":
        return PARAMS_FILE
    return os.path.join(CONFIG_PROJECT, f"{profile}_params.yaml")


def sorter_areas(params: dict | None = None) -> set:
    params = params if params is not None else load_params()
    return set(as_sheet_list(params.get("sorter_areas")))


def parse_params_by_type(blob: str) -> dict:
    """'<B1/2>p=1 | q=0<B1/2><DI1/2>r=0<DI1/2>' -> {'B1/2': 'p=1 | q=0', 'DI1/2': 'r=0'}."""
    import re
    out = {}
    for st, block in re.findall(r"<([^>]+)>(.*?)<\1>", blob or ""):
        out[st.strip().upper()] = block.strip()
    return out


def load_device_types_db(params: dict) -> dict:
    """Global DeviceTypesDatabase (delim-sniffed, manually maintained). Returns
    {by_id: {ID_upper -> rec}, default_cards: {parent_upper -> [card_id,...]}}."""
    import re
    path = params.get("device_types_db") or DEVICE_TYPES_DB_DEFAULT
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


def load_iolist_columns() -> list:
    """Canonical I/O List column names in position order (input_docs/iolist_columns.csv)."""
    rows = sorted(_read_csv("iolist_columns.csv"), key=lambda r: int(r["position"]))
    return [r["name"] for r in rows]


def load_permanent_parts() -> list:
    """Valid 'permanent part' descriptions (input_docs/iolist_permanent_parts.csv)."""
    return [r["permanent_part"] for r in _read_csv("iolist_permanent_parts.csv")
            if (r.get("permanent_part") or "").strip()]


def load_column_map(document: str) -> list:
    """Column map rows for one document:
    {column, canonical, expected_header, required(bool), preliminary_check_exclude(bool)}.
    `preliminary_check_exclude` marks pipeline-generated columns (AA-AG) that the phase-100
    standalone I/O List validation must ignore (they aren't part of the customer-authored doc)."""
    rows = []
    for r in _read_csv("column_map.csv"):
        if r["document"] != document:
            continue
        rows.append({
            "column": r["column"].strip(),
            "canonical": r["canonical"].strip(),
            "expected_header": r["expected_header"].strip(),
            "required": as_bool(r["required"]),
            "preliminary_check_exclude": as_bool(r.get("preliminary_check_exclude")),
        })
    return rows


def load_diagnosis_columns() -> list:
    """The >List_IO / >List_Logic column layout: [(header, expression)] from
    diagnosis/diagnosis_columns.csv."""
    return [(r["header"].strip(), (r.get("expression") or "").strip())
            for r in _read_csv("diagnosis_columns.csv", diagnosis_dir()) if (r.get("header") or "").strip()]


def load_rules(name: str, base: str | None = None) -> list:
    """Generic rule table (name, required_types, dev_type, db_name, member, interface_tagname,
    diag_desc). Used by datablock_elements_rules.csv (phase 400 interface mirroring, interfaces.py) and
    diagnosis_logic_rules.csv (List_Logic generation, phase 610). `required_types` is '|'-separated.
    `diag_desc` is the optional rule-supplied diagnosis description ({canonical} template) the 610
    List_Logic rows carry instead of the source signal's own diag_desc (blank -> keep the source's)."""
    rules = []
    for r in _read_csv(name, base):
        if not (r.get("name") or "").strip():
            continue
        rules.append({
            "name": (r.get("name") or "").strip(),
            "required_types": [t.strip() for t in (r.get("required_types") or "").split("|") if t.strip()],
            "dev_type": (r.get("dev_type") or "").strip(),
            "db_name": (r.get("db_name") or "").strip(),
            "member": (r.get("member") or "").strip(),
            "interface_tagname": (r.get("interface_tagname") or "").strip(),
            "diag_desc": (r.get("diag_desc") or "").strip(),
        })
    return rules


def load_interface_elements_rules(base: str | None = None) -> list:
    """Interface mirroring rules (phase 400): a mirrored signal of a matching script_type spawns an
    extra coupler element. Columns: name, required_types ('|'-separated trigger script_types),
    dev_type (optional filter), direction (I/Q - the ONLY source that may add an input row),
    data_type (BOOL/WORD), script_type (byte-grouping label; defaults to name), member (mirror-name
    template, {functional_unit}{location}{device} interpolated). Missing file -> []."""
    path = os.path.join(base or input_docs_dir(), "interface_elements_rules.csv")
    if not os.path.exists(path):
        return []
    rules = []
    for r in _read_csv("interface_elements_rules.csv", base):
        if not (r.get("name") or "").strip():
            continue
        direction = (r.get("direction") or "Q").strip().upper()
        data_type = (r.get("data_type") or "BOOL").strip().upper()
        rules.append({
            "name": (r.get("name") or "").strip(),
            "required_types": [t.strip() for t in (r.get("required_types") or "").split("|") if t.strip()],
            "dev_type": (r.get("dev_type") or "").strip(),
            "direction": "I" if direction == "I" else "Q",
            "data_type": "WORD" if data_type == "WORD" else "BOOL",
            "script_type": (r.get("script_type") or "").strip() or (r.get("name") or "").strip(),
            "member": (r.get("member") or "").strip(),
            "interface_tagname": (r.get("interface_tagname") or "").strip(),
        })
    return rules


def _b(value, default: bool) -> bool:
    """as_bool, but a blank cell falls back to `default` (the DB-config bool columns)."""
    s = str(value or "").strip()
    return as_bool(s) if s else default


def load_db_definitions(base: str | None = None) -> list:
    """The AUTHORITATIVE DB registry (phase 520): every data block, Global or an Instance family. Columns:
    db_name (literal or a PEP-3101 template for a family), db_type (Global|Instance), db_programming_language
    (DB|F_DB), instance_of (FB, for Instance), for_each (iteration DSL), memory_layout (Optimized|Standard),
    opc_ua/webserver/only_load_memory/write_protected/retain_reserve (bool), memory_reserve, create_when
    (always|if_elements|never), comment. Missing file -> []."""
    base = base or datablocks_dir()
    if not os.path.exists(os.path.join(base, "datablock_definitions.csv")):
        return []
    out = []
    for r in _read_csv("datablock_definitions.csv", base):
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
            "opc_ua": _b(r.get("opc_ua"), pl.upper() != "F_DB"),  # a blank cell defaults OFF for a fail-safe DB
            "webserver": _b(r.get("webserver"), True),
            "only_load_memory": _b(r.get("only_load_memory"), False),
            "write_protected": _b(r.get("write_protected"), False),
            "retain_reserve": _b(r.get("retain_reserve"), False),
            "memory_reserve": (r.get("memory_reserve") or "").strip(),
            "seed": _b(r.get("seed"), False),
            "create_when": (r.get("create_when") or "if_elements").strip().lower() or "if_elements",
            "comment": (r.get("comment") or "").strip(),
        })
    return out


def load_db_elements(base: str | None = None) -> list:
    """The Global-DB members (phase 520). Columns: db_name, member (PEP-3101 template), for_each (iteration
    DSL), datatype, start_value, retain (bool), ext_accessible/ext_visible/ext_writable (bool), setpoint
    (bool), comment. Missing file -> []."""
    base = base or datablocks_dir()
    if not os.path.exists(os.path.join(base, "datablock_elements.csv")):
        return []
    out = []
    for r in _read_csv("datablock_elements.csv", base):
        if not (r.get("db_name") or "").strip():
            continue
        out.append({
            "db_name": (r.get("db_name") or "").strip(),
            "member": (r.get("member") or "").strip(),
            "for_each": (r.get("for_each") or "").strip(),
            "datatype": (r.get("datatype") or "").strip() or "Bool",
            "start_value": (r.get("start_value") or "").strip(),
            "retain": _b(r.get("retain"), False),
            "ext_accessible": _b(r.get("ext_accessible"), True),
            "ext_visible": _b(r.get("ext_visible"), True),
            "ext_writable": _b(r.get("ext_writable"), True),
            "setpoint": _b(r.get("setpoint"), False),
            "comment": (r.get("comment") or "").strip(),
        })
    return out


def load_db_types(base: str | None = None) -> list:
    """The valid member data types (phase 520 validation). Columns: name, kind (Elementary|UDT), comment.
    Missing file -> []."""
    base = base or datablocks_dir()
    if not os.path.exists(os.path.join(base, "datablock_types.csv")):
        return []
    out = []
    for r in _read_csv("datablock_types.csv", base):
        if not (r.get("name") or "").strip():
            continue
        out.append({"name": (r.get("name") or "").strip(),
                    "kind": (r.get("kind") or "Elementary").strip() or "Elementary",
                    "comment": (r.get("comment") or "").strip()})
    return out


def load_signal_types() -> dict:
    """type_id (upper) -> type record. Names/comments are {canonical}-interpolation templates
    resolved per row (see plan §2). Paired channel-2 types inherit the sibling's tagtable_name."""
    types = {}
    for r in _read_csv("signal_types.csv"):
        tid = (r.get("type_id") or "").strip()
        db_names = [n.strip() for n in (r.get("db_names") or "").split("|") if n.strip()]
        types[tid.upper()] = {
            "type_id": tid,
            "type_id_desc": (r.get("type_id_desc") or "").strip(),
            "category": (r.get("category") or "").strip(),
            "pair_key": (r.get("pair_key") or "").strip(),
            "channel": (r.get("channel") or "").strip(),
            "is_pattern": as_bool(r.get("is_pattern")),
            "tagtable_name": (r.get("tagtable_name") or "").strip(),
            "tag_name": (r.get("tag_name") or "").strip(),
            "db_names": db_names,   # the DB(s) this signal is a member of; the registry owns each DB's ProgrammingLanguage
            "db_element": (r.get("db_element") or "").strip(),
            "in_diagnosis": as_bool(r.get("in_diag")),
            "diagnosis_logic": (r.get("diag_logic") or "").strip().lower(),
            "diag_desc": (r.get("diag_desc") or "").strip(),
            "io_comment": (r.get("io_comment") or "").strip(),
            "ce_mandatory": (r.get("ce_mandatory") or "").strip().lower(),
            "diag_container_check": (r.get("diag_container_check") or "").strip(),
            "interface_tagname": (r.get("interface_tagname") or "").strip(),
        }
    by_pair = {}
    for t in types.values():
        if t["pair_key"] and t["tagtable_name"]:
            by_pair.setdefault(t["pair_key"], t["tagtable_name"])
    for t in types.values():
        if not t["tagtable_name"] and t["pair_key"] in by_pair:
            t["tagtable_name"] = by_pair[t["pair_key"]]
    return types


def resolve_type(types: dict, raw_type) -> dict | None:
    """Resolve a raw type cell to a signal_types record, honoring pattern types (Z# matches Z1,
    Z2, ...). Returns None when unknown/blank."""
    if raw_type is None:
        return None
    clean = str(raw_type).strip()
    if clean == "":
        return None
    exact = types.get(clean.upper())
    if exact:
        return exact
    for rec in types.values():
        if not rec["is_pattern"]:
            continue
        prefix = rec["type_id"].split("#")[0].upper()
        rest = clean.upper()[len(prefix):] if clean.upper().startswith(prefix) else ""
        if rest and rest.isdigit():
            return rec
    return None
