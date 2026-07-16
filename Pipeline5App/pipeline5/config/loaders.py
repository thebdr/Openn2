"""The config-CSV readers: rulesets, type registries, and the device-types database.

Everything here reads a hand-editable CSV through `read_config_csv` (the SAME JSON-cell codec as the
SSOT tables, tolerant of hand edits) and returns plain dicts/lists. Grouped by the phase that consumes
them: ph200 classification rules · the signal-type registry · diagnosis · chain-reactions/interfaces ·
the ph520 data-block registry · the ph700 DeviceTypesDatabase.
"""
from __future__ import annotations

import csv
import os
import re

from pipeline5.config.paths import (
    DEVICE_TYPES_DB_DEFAULT,
    chain_reactions_dir,
    datablocks_dir,
    diagnosis_dir,
    input_docs_dir,
)


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
    from pipeline5.truth.table import decode_cell
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


def load_seed_members() -> list:
    """generation_params.yaml `datablocks.seed_members` - the Bool seed members every `seed: true`
    DB starts with. STRICT: a missing key is a located error, never an in-code default (the
    config-completeness rule). Consumed by the 520 generator AND the 900 coverage pads."""
    from pipeline5.config.params import load_generation_params
    section = (load_generation_params() or {}).get("datablocks") or {}
    try:
        return [str(x) for x in section["seed_members"]]
    except (KeyError, TypeError):
        raise RuntimeError("generation_params.yaml: datablocks.seed_members is missing") from None
