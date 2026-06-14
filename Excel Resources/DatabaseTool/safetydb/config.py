"""Loads the versioned config (CSV tables + params.json) from the config/ dir."""
from __future__ import annotations
import csv
import json
import os

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # DatabaseTool/
CONFIG_DIR = os.path.join(_HERE, "config")

_TRUE = {"yes", "true", "1", "y"}


def _sniff_delim(text: str) -> str:
    """',' unless the first non-empty line clearly uses ';' more (transition-safe)."""
    first = next((ln for ln in text.splitlines() if ln.strip()), "")
    return ";" if first.count(";") > first.count(",") else ","


def _read_csv(name: str) -> list[dict]:
    path = os.path.join(CONFIG_DIR, name)
    with open(path, newline="", encoding="utf-8-sig") as f:
        text = f.read()
    return list(csv.DictReader(text.splitlines(), delimiter=_sniff_delim(text)))


def as_bool(value) -> bool:
    return str(value).strip().lower() in _TRUE


def load_params(path: str | None = None) -> dict:
    path = path or os.path.join(CONFIG_DIR, "params.json")
    with open(path, encoding="utf-8") as f:
        params = json.load(f)
    # resolve document paths relative to DatabaseTool/ so the tool runs from anywhere
    for key in ("io_list", "ce"):
        if key in params and not os.path.isabs(params[key]["path"]):
            params[key] = dict(params[key], path=os.path.normpath(os.path.join(_HERE, params[key]["path"])))
    if "device_types_db" in params and not os.path.isabs(params["device_types_db"]):
        params["device_types_db"] = os.path.normpath(os.path.join(_HERE, params["device_types_db"]))
    return params


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
    path = params["device_types_db"]
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


def load_signal_types() -> dict:
    """type_id (upper) -> {type_id, description, category, pair_key, channel,
    in_diagnosis(bool), is_pattern(bool), db_kind, db_names(list), add_to_name,
    tagtable_name}."""
    types = {}
    for r in _read_csv("signal_types.csv"):
        tid = (r.get("type_id") or "").strip()
        # db_names: '|'-separated; a type may feed several (identical) DBs.
        # 'db_name' (legacy single) is still accepted as a fallback.
        raw_names = (r.get("db_names") or r.get("db_name") or "").strip()
        db_names = [n.strip() for n in raw_names.split("|") if n.strip()]
        types[tid.upper()] = {
            "type_id": tid,
            "description": (r.get("description") or "").strip(),
            "category": (r.get("category") or "").strip(),
            "pair_key": (r.get("pair_key") or "").strip(),
            "channel": (r.get("channel") or "").strip(),
            "in_diagnosis": as_bool(r.get("in_diagnosis")),
            "is_pattern": as_bool(r.get("is_pattern")),
            # db_kind: "" none | "db" standard DB | "safe_db" fail-safe (F) DB
            "db_kind": (r.get("db_kind") or "").strip().lower(),
            # db_names: target DBs; types may share one (E1/2 + B1/2 -> 01_Pushbutton)
            "db_names": db_names,
            # add_to_name: text appended to each DB member name; '{canonical}'
            # tokens are replaced by that column's value from the source row.
            "add_to_name": (r.get("add_to_name") or "").strip(),
            # tagtable_name: PLC tag-table (Path) the type's I/O tags belong to.
            "tagtable_name": (r.get("tagtable_name") or "").strip(),
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
