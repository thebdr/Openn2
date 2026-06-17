"""Loads the versioned config (CSV tables + project_params.yaml) and resolves the _Openn2 layout.

Layout (this module sits at Pipeline2App/pipeline2/core/config.py):
  Pipeline2App/                       <- APP_ROOT
    config_project/                   <- per-project config (CONFIG_PROJECT)
      project_params.yaml             <- PARAMS_FILE
      input_docs/  *.csv              <- column_map, signal_types, iolist_columns, iolist_permanent_parts
      diagnosis/   *.csv              <- diagnosis_columns, diagnosis_logic_rules
      block_templates.json            <- BLOCK_TEMPLATES_JSON
    user_input/  error_management.csv <- USER_INPUT (user-edited treatments, persists between runs)
  ../Shared/                          <- SHARED (the handoff with Open2App)
    Templates/                        <- TEMPLATES_DIR (TIA software blocks + machine interfaces)
    HardwareConfigBuilderData/DeviceTypesDatabase.csv
    OutputTree/                       <- OUTPUT_ROOT (every generated artifact)
"""
from __future__ import annotations
import csv
import json
import os
import sys

# APP_ROOT = the Pipeline2App dir (dev: this file's grandparent; frozen: the bundle/exe dir).
if getattr(sys, "frozen", False):
    APP_ROOT = getattr(sys, "_MEIPASS", None) or os.path.dirname(sys.executable)
else:
    # pipeline2/core/config.py -> core -> pipeline2 -> Pipeline2App
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
BLOCK_TEMPLATES_JSON = os.path.join(CONFIG_PROJECT, "block_templates.json")
CONFIG_DIR = CONFIG_PROJECT                # alias: "open the config folder" = the project config

# Shared-data defaults (used when project_params.yaml omits / can't resolve them):
DEVICE_TYPES_DB_DEFAULT = os.path.join(SHARED, "HardwareConfigBuilderData", "DeviceTypesDatabase.csv")
INTERFACE_TEMPLATE_DEFAULT = os.path.join(TEMPLATES_DIR, "MachineInterfaces", "TEMPLATE_INTERFACES_v0.0.xlsx")

# Generated outputs land under the run's output root (default OUTPUT_ROOT = Shared/OutputTree) at
# these semantic subpaths - the handoff tree Open2App imports. Writers join these under the root.
OUTPUT_PATHS = {
    "validation_report":   os.path.join("Reports", "documents_validation_report"),    # + .txt / .html
    "coverage_report":     os.path.join("Reports", "io_project_coverage_report"),      # + .csv / .txt
    "io_database":         os.path.join("ProjectDocumentation", "InformationDatabase", "IODatabase.csv"),
    "diagnosis_dir":       os.path.join("ProjectDocumentation", "InformationDatabase", "DiagnosisData"),
    "interfaces_dir":      os.path.join("ProjectDocumentation", "InformationDatabase", "Interfaces"),
    "hardware_dir":        os.path.join("TiaPortalProjectInterface", "BuilderData", "HardwareConfiguration"),
    "blocks_creation_dir": os.path.join("TiaPortalProjectInterface", "BuilderData", "SoftwareBlocks", "CreationInfo"),
    "blocks_import_dir":   os.path.join("TiaPortalProjectInterface", "BuilderData", "SoftwareBlocks", "ImportReady"),
    "io_tags_dir":         os.path.join("TiaPortalProjectInterface", "BuilderData", "PlcTags"),
}


def output_root(params: dict | None = None) -> str:
    """Root of the generated-artifact tree. Default = OUTPUT_ROOT (Shared/OutputTree); an absolute
    `params['output_dir']` overrides it (e.g. a self-contained project folder)."""
    d = (params or {}).get("output_dir")
    return d if (d and os.path.isabs(d)) else OUTPUT_ROOT


def out_path(out_root: str, key: str, *extra) -> str:
    """A generated-output path: `<out_root>/<OUTPUT_PATHS[key]>[/<extra...>]`."""
    return os.path.join(out_root, OUTPUT_PATHS[key], *extra)

_TRUE = {"yes", "true", "1", "y"}


def _sniff_delim(text: str) -> str:
    """',' unless the first non-empty line clearly uses ';' more (transition-safe)."""
    first = next((ln for ln in text.splitlines() if ln.strip()), "")
    return ";" if first.count(";") > first.count(",") else ","


def _read_csv(name: str, base: str | None = None) -> list[dict]:
    path = os.path.join(base or INPUT_DOCS_DIR, name)
    with open(path, newline="", encoding="utf-8-sig") as f:
        text = f.read()
    return list(csv.DictReader(text.splitlines(), delimiter=_sniff_delim(text)))


def as_bool(value) -> bool:
    return str(value).strip().lower() in _TRUE


def as_sheet_list(value) -> list:
    """params io_list 'sheet' / ce 'matrix_sheet' may be a single name or a list -> list of
    pattern strings (each is a regex, see resolve_sheets)."""
    if isinstance(value, (list, tuple)):
        return [str(s).strip() for s in value if str(s).strip()]
    s = str(value or "").strip()
    return [s] if s else []


def resolve_sheets(patterns, available) -> list:
    """Match sheet-name `patterns` (each a **regex**, case-insensitive, `re.search`; an invalid
    regex falls back to an exact, case-insensitive name match) against the workbook's `available`
    sheet names. Returns the matching names in workbook order, de-duplicated."""
    import re
    pats = as_sheet_list(patterns)
    compiled = []
    for p in pats:
        try:
            compiled.append(("re", re.compile(p, re.IGNORECASE)))
        except re.error:
            compiled.append(("lit", p.lower()))         # not a valid regex -> literal match
    out = []
    for name in available:
        for kind, p in compiled:
            if (p.search(name) if kind == "re" else p == name.lower()):
                out.append(name)
                break
    return out


def resolve_sheet(pattern, available) -> str | None:
    """The first sheet name matching `pattern` (regex), or None. For single-sheet contexts
    (the C&E matrix sheet)."""
    m = resolve_sheets(pattern, available)
    return m[0] if m else None


def _read_params_file(path: str) -> dict:
    """Load a params file as a plain dict. YAML (.yaml/.yml) via ruamel's safe loader;
    .json via the stdlib (backward compatible with the old params.json)."""
    if path.lower().endswith((".yaml", ".yml")):
        from ruamel.yaml import YAML
        with open(path, encoding="utf-8") as f:
            return dict(YAML(typ="safe").load(f) or {})
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _resolve_doc(base: str, rel: str) -> str:
    """Resolve a relative document path against `base` (the params file's own directory)."""
    return os.path.normpath(os.path.join(base, rel))


def load_params(path: str | None = None) -> dict:
    path = path or PARAMS_FILE
    params = _read_params_file(path)
    # resolve document paths relative to the params file's directory (so a project is portable)
    base = os.path.dirname(os.path.abspath(path))
    for key in ("io_list", "ce"):
        if key in params and params[key].get("path") and not os.path.isabs(params[key]["path"]):
            params[key] = dict(params[key], path=_resolve_doc(base, params[key]["path"]))
    # shared-data docs: an absolute path wins; a relative one resolves against the project (else the
    # Shared default); an absent key falls back to the Shared default.
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
    """Areas flagged as sorter-style, from params.yaml 'sorter_areas' (a list of AREA names)."""
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
    """Global DeviceTypesDatabase (';'-delimited, manually maintained). Returns
    {by_id: {ID_upper -> rec}, default_cards: {parent_upper -> [card_id,...]}}.
    rec = {model_id, dev_type, order, comment, params, params_by_type(dict),
    io_addr_params, parent}. A card whose Identifier is '<PARENT>:SUFFIX' is a
    default card of PARENT (emitted as a Modules row per station of PARENT)."""
    import re
    path = params.get("device_types_db") or DEVICE_TYPES_DB_DEFAULT
    by_id, default_cards = {}, {}
    with open(path, encoding="utf-8-sig") as f:
        text = f.read()
    # sniff delimiter from the first non-comment line (',' or ';')
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


def load_iolist_columns() -> list[str]:
    """The canonical I/O List column names in position order (config_project/input_docs/iolist_columns.csv),
    ported verbatim from the external IOList-check tool's '_' glossary. Drives Phase 0A's
    positional column-name check. Compared via iolist_checks._clean (whitespace-insensitive)."""
    rows = sorted(_read_csv("iolist_columns.csv"), key=lambda r: int(r["position"]))
    return [r["name"] for r in rows]


def load_permanent_parts() -> list[str]:
    """The valid 'permanent part' descriptions (config_project/input_docs/iolist_permanent_parts.csv), ported verbatim
    from the external tool's '_' glossary. Phase 0A flags A/W rows whose desc_l1 (col K) is not
    in this list. Compared via iolist_checks._clean (whitespace-insensitive)."""
    return [r["permanent_part"] for r in _read_csv("iolist_permanent_parts.csv")
            if (r.get("permanent_part") or "").strip()]


def load_column_map(document: str) -> list[dict]:
    """Rows for one document: {column, canonical, expected_header, required(bool)}."""
    rows = []
    for r in _read_csv("column_map.csv"):
        if r["document"] != document:
            continue
        rows.append({
            "column": r["column"].strip(),
            "canonical": r["canonical"].strip(),
            "expected_header": r["expected_header"].strip(),
            "required": as_bool(r["required"]),
        })
    return rows


def load_diagnosis_columns() -> list[tuple]:
    """The >List_IO / >List_Logic column layout: [(header, expression)] from
    config_project/diagnosis/diagnosis_columns.csv. `expression` interpolates CentralDatabase columns with
    `{canonical}` tokens (literals allowed); the sentinel `$PLC_Binding$` is computed by
    outputs.plc_binding (the only hardcoded column)."""
    return [(r["header"].strip(), (r.get("expression") or "").strip())
            for r in _read_csv("diagnosis_columns.csv", DIAGNOSIS_DIR) if (r.get("header") or "").strip()]


def load_signal_types() -> dict:
    """type_id (upper) -> type record. Names/comments are `{canonical}`-interpolation
    TEMPLATES resolved per row (see outputs._interp): `tag_name` (I/O tag), `db_element`
    (DB member), `io_comment` (tag/member comment), `diag_desc` (diagnosis description).
    Also: type_id_desc, category, pair_key, channel, is_pattern, db_kind, db_names(list),
    in_diagnosis(bool), diagnosis_logic, tagtable_name."""
    types = {}
    for r in _read_csv("signal_types.csv"):
        tid = (r.get("type_id") or "").strip()
        raw_names = (r.get("db_names") or "").strip()
        db_names = [n.strip() for n in raw_names.split("|") if n.strip()]
        types[tid.upper()] = {
            "type_id": tid,
            "type_id_desc": (r.get("type_id_desc") or "").strip(),
            "category": (r.get("category") or "").strip(),
            "pair_key": (r.get("pair_key") or "").strip(),
            "channel": (r.get("channel") or "").strip(),
            "is_pattern": as_bool(r.get("is_pattern")),
            # tagtable_name: PLC tag-table (Path) the type's I/O tags belong to.
            "tagtable_name": (r.get("tagtable_name") or "").strip(),
            # tag_name: I/O tag-name template ('' -> the type is not tagged on its own,
            # e.g. a channel-2 type that shares its sibling's device tag).
            "tag_name": (r.get("tag_name") or "").strip(),
            # db_kind: "" none | "db" standard DB | "safe_db" fail-safe (F) DB
            "db_kind": (r.get("db_kind") or "").strip().lower(),
            # db_names: target DBs; types may share one (E1/2 + B1/2 -> 01_Pushbutton)
            "db_names": db_names,
            # db_element: DB-member-name template (the full member name, not a suffix).
            "db_element": (r.get("db_element") or "").strip(),
            "in_diagnosis": as_bool(r.get("in_diag")),
            # diagnosis_logic: mirror -> ML TRUE, invert -> ML FALSE, blank -> from
            # the row's normal_condition (see outputs.ml_value).
            "diagnosis_logic": (r.get("diag_logic") or "").strip().lower(),
            # diag_desc: diagnosis alarm/warning description template.
            "diag_desc": (r.get("diag_desc") or "").strip(),
            # io_comment: I/O tag + DB-member comment template.
            "io_comment": (r.get("io_comment") or "").strip(),
            # ce_mandatory: reverse-C&E rule (validation.check_ce_mandatory). 'yes' -> the
            # device must appear in the C&E (else ERROR); 'warn' -> same but WARNING;
            # 'no'/'' -> not required (the row is ignored by that check).
            "ce_mandatory": (r.get("ce_mandatory") or "").strip().lower(),
        }
    # A paired channel-2 type (e.g. E2/2) usually leaves tagtable_name blank; let it
    # inherit the sibling's table (same pair_key) so both channels of one device land
    # in the same PLC tag table. (An explicit tagtable_name always wins.)
    by_pair = {}
    for t in types.values():
        if t["pair_key"] and t["tagtable_name"]:
            by_pair.setdefault(t["pair_key"], t["tagtable_name"])
    for t in types.values():
        if not t["tagtable_name"] and t["pair_key"] in by_pair:
            t["tagtable_name"] = by_pair[t["pair_key"]]
    return types


def resolve_type(types: dict, raw_type) -> dict | None:
    """Resolves a raw type cell to a signal_types record, honoring pattern types
    (FA# matches FA1, FA2, ...). Returns None when unknown."""
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
