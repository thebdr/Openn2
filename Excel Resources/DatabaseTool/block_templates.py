#!/usr/bin/env python3
"""block_templates.py - block-template tooling (NOT part of the pipeline).

The TIA Portal Software Block templates under
`Templates/Tia Portal Software Blocks/*.xml` contain placeholders of the form
`!!key$$` (e.g. `!!NetworkComment$$`, `!!Error_memberOf:03_FDBACK$$`). This tool:

  keys    - scans every template for its distinct !!key$$ placeholders and writes
            `config/block_templates.json` = { template : { key : <binding> } }.
            Re-running MERGES: existing template/key bindings are preserved and only
            new templates/keys are added (nothing you filled in is overwritten).
            A new key's binding starts as "" (unbound). Bind it (by hand, or in the
            Files editor) to one of:
              * a canonical column name  -> "device"        (value from the row)
              * a literal list           -> ["a", "b", "c"]
              * a query over the staged DB (object; schema TBD when generation lands)

  staged  - exports the staged database to Output/CentralDatabase.csv (open it in the
            Pipeline2 Files tab and use the regex row filter to prototype queries).

Usage:
  python block_templates.py keys
  python block_templates.py staged [--out PATH]
"""
from __future__ import annotations
import argparse
import csv as _csv
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from safetydb import config

TEMPLATES_DIR = os.path.join(_HERE, "Templates", "Tia Portal Software Blocks")
TEMPLATES_JSON = os.path.join(config.CONFIG_DIR, "block_templates.json")
# !!key$$  - key is one or more chars that are not '$' or a line break (so a
# placeholder can't accidentally span lines or swallow a following '$').
KEY_RE = re.compile(r"!!([^$\r\n]+?)\$\$")


def _abs(path: str) -> str:
    return path if os.path.isabs(path) else os.path.normpath(os.path.join(_HERE, path))


def scan_template_keys(templates_dir: str = TEMPLATES_DIR) -> dict:
    """template name (file stem) -> list of distinct keys (first-seen order)."""
    out = {}
    if not os.path.isdir(templates_dir):
        raise SystemExit(f"templates folder not found: {templates_dir}")
    for name in sorted(os.listdir(templates_dir)):
        if not name.lower().endswith(".xml"):
            continue
        with open(os.path.join(templates_dir, name), encoding="utf-8") as f:
            text = f.read()
        keys = list(dict.fromkeys(KEY_RE.findall(text)))  # dedup, keep order
        out[os.path.splitext(name)[0]] = keys
    return out


def build_templates_json(templates_dir: str = TEMPLATES_DIR, json_path: str = TEMPLATES_JSON) -> dict:
    """Merge scanned keys into block_templates.json, preserving existing bindings.
    Returns a summary: added_templates, added_keys, kept_keys, missing (orphan keys)."""
    scanned = scan_template_keys(templates_dir)
    existing = {}
    if os.path.exists(json_path):
        with open(json_path, encoding="utf-8") as f:
            existing = json.load(f)

    result = dict(existing)  # keep any templates that weren't re-scanned, too
    added_t = added_k = kept_k = 0
    missing = []
    for tname, keys in scanned.items():
        block = dict(existing.get(tname, {}))
        if tname not in existing:
            added_t += 1
        for k in keys:
            if k in block:
                kept_k += 1
            else:
                block[k] = ""  # unbound; the user binds it later
                added_k += 1
        # bindings present in the JSON but no longer in the template - keep, but note
        for k in existing.get(tname, {}):
            if k not in keys:
                missing.append(f"{tname} / {k}")
        result[tname] = block

    os.makedirs(os.path.dirname(json_path), exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
        f.write("\n")
    return {"added_templates": added_t, "added_keys": added_k, "kept_keys": kept_k, "missing": missing}


def dump_staged(csv_path: str | None = None, params_path: str | None = None) -> str:
    """Write the staged I/O List rows to a CSV (canonical columns + a few resolved
    fields) for inspection. Returns the path written."""
    from safetydb import staging  # local import so `keys` doesn't need the I/O List
    params = config.load_params(params_path)
    types = config.load_signal_types()
    rows, _warnings = staging.load_io_list(params, types)  # adds matrix_areas (in staging now)
    cols = [m["canonical"] for m in config.load_column_map("IoList")]
    extra = ["matrix_areas", "_source_sheet", "_source_row", "type_id_resolved", "type_category"]
    csv_path = csv_path or os.path.join(_abs(params.get("output_dir", "Output")), "CentralDatabase.csv")
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        w = _csv.writer(f, lineterminator="\n")
        w.writerow(cols + extra)
        for r in rows:
            t = r.get("_type") or {}
            w.writerow([r.get(c, "") for c in cols]
                       + [r.get("matrix_areas", ""), r.get("_source_sheet", ""),
                          r.get("_source_row", ""), t.get("type_id", ""), t.get("category", "")])
    return csv_path


def main():
    ap = argparse.ArgumentParser(description="Block-template tooling (not part of the pipeline).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("keys", help="scan templates -> config/block_templates.json (merge)")
    sp = sub.add_parser("staged", help="export the staged database to CSV for inspection")
    sp.add_argument("--out", default=None, help="output CSV path (default Output/CentralDatabase.csv)")
    args = ap.parse_args()

    if args.cmd == "keys":
        s = build_templates_json()
        print(f"block_templates.json: +{s['added_templates']} template(s), "
              f"+{s['added_keys']} new key(s), {s['kept_keys']} kept binding(s)")
        for m in s["missing"]:
            print(f"  (note) key no longer in template, binding kept: {m}")
        print(f"  -> {TEMPLATES_JSON}")
    elif args.cmd == "staged":
        print(f"staged database -> {dump_staged(args.out)}")


if __name__ == "__main__":
    main()
