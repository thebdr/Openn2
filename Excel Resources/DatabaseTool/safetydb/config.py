"""Loads the versioned config (CSV tables + params.json) from the config/ dir."""
from __future__ import annotations
import csv
import json
import os

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # DatabaseTool/
CONFIG_DIR = os.path.join(_HERE, "config")

_TRUE = {"yes", "true", "1", "y"}


def _read_csv(name: str) -> list[dict]:
    path = os.path.join(CONFIG_DIR, name)
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f, delimiter=";"))


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


def load_device_types_db(params: dict) -> dict:
    """Global DeviceTypesDatabase (manually maintained): Model Id (upper) ->
    {model_id, dev_type, order, comment, params}. '#'-comment lines skipped."""
    path = params["device_types_db"]
    db = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line or line.lstrip().startswith("#"):
                continue
            cells = line.split(";")
            model = cells[0].strip()
            if not model:
                continue
            db[model.upper()] = {
                "model_id": model,
                "dev_type": cells[1].strip() if len(cells) > 1 else "",
                "order": cells[2].strip() if len(cells) > 2 else "",
                "comment": cells[3].strip() if len(cells) > 3 else "",
                "params": cells[4].strip() if len(cells) > 4 else "",
            }
    return db


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
    in_diagnosis(bool), is_pattern(bool)}."""
    types = {}
    for r in _read_csv("signal_types.csv"):
        tid = r["type_id"].strip()
        types[tid.upper()] = {
            "type_id": tid,
            "description": r["description"].strip(),
            "category": r["category"].strip(),
            "pair_key": r["pair_key"].strip(),
            "channel": r["channel"].strip(),
            "in_diagnosis": as_bool(r["in_diagnosis"]),
            "is_pattern": as_bool(r["is_pattern"]),
            # db_kind: "" none | "db" standard DB | "safe_db" fail-safe (F) DB
            "db_kind": (r.get("db_kind") or "").strip().lower(),
            # db_name: target DB name; types may share one (E1/2 + B1/2 -> 01_Pushbutton)
            "db_name": (r.get("db_name") or "").strip(),
        }
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
