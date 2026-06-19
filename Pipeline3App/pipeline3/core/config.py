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
BLOCK_TEMPLATES_JSON = os.path.join(CONFIG_PROJECT, "block_templates.json")
CONFIG_DIR = CONFIG_PROJECT                # alias: "open the config folder"

# Where New / Save As create a project (a self-contained <PROJECTS_DIR>/<name> directory). The
# default is overridable by the PIPELINE3_PROJECTS env var AND, at runtime, user-selectable
# (persisted by the GUI) - see plan §4 Project Manager.
PROJECTS_DIR = os.environ.get("PIPELINE3_PROJECTS") or os.path.join(os.path.expanduser("~"), "Pipeline3 Projects")

# Shared-data defaults (used when project_params.yaml omits / can't resolve them):
DEVICE_TYPES_DB_DEFAULT = os.path.join(SHARED, "HardwareConfigBuilderData", "DeviceTypesDatabase.csv")
INTERFACE_TEMPLATE_DEFAULT = os.path.join(TEMPLATES_DIR, "MachineInterfaces", "TEMPLATE_INTERFACES_v0.0.xlsx")

# Generated outputs land under the run's output root (default OUTPUT_ROOT = Shared/OutputTree) at
# these semantic subpaths. The BuilderData/* keys are the Open2App import contract (keep stable).
OUTPUT_PATHS = {
    # --- documentation / intermediate (NOT imported by Open2App) --- #
    "validation_report":   os.path.join("Reports", "documents_validation_report"),     # + .txt / .html (complete log)
    "validation_errors":   os.path.join("Reports", "documents_validation_errors"),      # + .txt / .html (errors-only view)
    "coverage_report":     os.path.join("Reports", "io_project_coverage_report"),       # + .csv / .txt
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
    path = os.path.join(base or INPUT_DOCS_DIR, name)
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
            for r in _read_csv("diagnosis_columns.csv", DIAGNOSIS_DIR) if (r.get("header") or "").strip()]


def load_rules(name: str, base: str | None = None) -> list:
    """Generic rule table (name, required_types, dev_type, db_name, member). Used by both
    datablock_elements_rules.csv (DB element generation, phase 520) and diagnosis_logic_rules.csv
    (List_Logic generation, phase 610). `required_types` is '|'-separated."""
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
        })
    return rules


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
            "db_kind": (r.get("db_kind") or "").strip().lower(),
            "db_names": db_names,
            "db_element": (r.get("db_element") or "").strip(),
            "in_diagnosis": as_bool(r.get("in_diag")),
            "diagnosis_logic": (r.get("diag_logic") or "").strip().lower(),
            "diag_desc": (r.get("diag_desc") or "").strip(),
            "io_comment": (r.get("io_comment") or "").strip(),
            "ce_mandatory": (r.get("ce_mandatory") or "").strip().lower(),
            "diag_container_check": (r.get("diag_container_check") or "").strip(),
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
