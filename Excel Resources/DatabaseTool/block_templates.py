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
import ast
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
BUILDERS_PY = os.path.join(_HERE, "block_builders.py")
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


# --- block_builders.py scaffolder -------------------------------------------
_STUB = ('# $replace\n'
         'def {name}(db: list) -> list:\n'
         '    """{stem}.xml - TODO: gather instances.\n'
         '    keys: {keys}\n'
         '    """\n'
         '    return []')


def _builder_func_name(stem: str) -> str:
    """Template stem -> builder function name, e.g. ...--03_Zone Cumulative -> build_03_zone_cumulative."""
    part = stem.rsplit("--", 1)[-1]
    return "build_" + (re.sub(r"[^a-z0-9]+", "_", part.lower()).strip("_") or "template")


def sync_builders(builders_path: str = BUILDERS_PY, json_path: str = TEMPLATES_JSON) -> dict:
    """Regenerate block_builders.py from block_templates.json, honoring the per-builder
    markers: a function above which sits `# $replace` (or that doesn't exist yet) is
    re-stubbed with that template's current keys; `# $keep` (or no marker) is preserved
    verbatim. The header (docstring/helpers) and trailing content are kept; the BUILDERS
    dict is regenerated. Returns {kept, replaced, added}."""
    with open(json_path, encoding="utf-8") as f:
        templates = json.load(f)
    src = open(builders_path, encoding="utf-8").read()
    lines = src.splitlines()
    tree = ast.parse(src)

    # existing build_* functions: name -> {marker, block, start(1-based)}
    builders, first_line = {}, None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name.startswith("build_"):
            j, marker, mstart = node.lineno - 2, None, node.lineno
            while j >= 0 and lines[j].strip() == "":
                j -= 1
            if j >= 0:
                m = re.match(r"#\s*\$\s*(keep|replace)\b", lines[j].strip())
                if m:
                    marker, mstart = m.group(1), j + 1
            builders[node.name] = {"marker": marker, "block": "\n".join(lines[mstart - 1:node.end_lineno])}
            first_line = mstart if first_line is None else min(first_line, mstart)

    # existing stem -> funcname (from the BUILDERS dict) + the dict's extent
    existing_map, assign = {}, None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "BUILDERS" for t in node.targets):
            assign = node
            if isinstance(node.value, ast.Dict):
                for k, v in zip(node.value.keys, node.value.values):
                    if isinstance(k, ast.Constant) and isinstance(v, ast.Name):
                        existing_map[k.value] = v.id

    header_end = (first_line - 1) if first_line else (assign.lineno - 1 if assign else len(lines))
    header = "\n".join(lines[:header_end]).rstrip()
    trailing = "\n".join(lines[assign.end_lineno:]).strip() if assign else ""

    blocks, new_map, kept = [], {}, 0
    replaced = added = 0
    for stem, keys in templates.items():
        fname = existing_map.get(stem) or _builder_func_name(stem)
        new_map[stem] = fname
        ex = builders.get(fname)
        if ex and ex["marker"] != "replace":           # $keep or no marker -> preserve
            blocks.append(ex["block"]); kept += 1
        else:                                           # $replace or new -> (re)stub
            blocks.append(_STUB.format(name=fname, stem=stem, keys=", ".join(keys.keys())))
            replaced += int(bool(ex)); added += int(not ex)

    dict_src = ["# template file stem -> builder", "BUILDERS = {"]
    dict_src += [f"    {stem!r}: {new_map[stem]}," for stem in templates]
    dict_src.append("}")

    out = header + "\n\n\n" + "\n\n\n".join(blocks) + "\n\n\n" + "\n".join(dict_src) + "\n"
    if trailing:
        out += "\n" + trailing + "\n"
    with open(builders_path, "w", encoding="utf-8") as f:
        f.write(out)
    return {"kept": kept, "replaced": replaced, "added": added}


def dump_staged(csv_path: str | None = None, params_path: str | None = None) -> str:
    """Write the staged I/O List rows to a CSV (canonical columns + a few resolved
    fields) for inspection. Returns the path written."""
    from safetydb import staging  # local import so `keys` doesn't need the I/O List
    params = config.load_params(params_path)
    types = config.load_signal_types()
    rows, _warnings = staging.load_io_list(params, types)  # adds matrix_areas (in staging now)
    cols = [m["canonical"] for m in config.load_column_map("IoList")]
    extra = ["matrix_areas", "IsSorterArea", "name_in_db", "subnet_name",
             "I_startByte", "I_endByte", "Q_startByte", "Q_endByte",
             "_source_sheet", "_source_row", "type_id_resolved", "type_category"]
    csv_path = csv_path or os.path.join(_abs(params.get("output_dir", "Output")), "CentralDatabase.csv")
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        w = _csv.writer(f, lineterminator="\n")
        w.writerow(cols + extra)
        for r in rows:
            t = r.get("_type") or {}
            w.writerow([r.get(c, "") for c in cols]
                       + [r.get("matrix_areas", ""), r.get("IsSorterArea", ""),
                          r.get("name_in_db", ""), r.get("subnet_name", ""),
                          r.get("I_startByte", ""), r.get("I_endByte", ""),
                          r.get("Q_startByte", ""), r.get("Q_endByte", ""),
                          r.get("_source_sheet", ""), r.get("_source_row", ""),
                          t.get("type_id", ""), t.get("category", "")])
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
        b = sync_builders()
        print(f"block_builders.py: {b['kept']} kept ($keep), {b['replaced']} re-stubbed "
              f"($replace), {b['added']} added  -> {BUILDERS_PY}")
    elif args.cmd == "staged":
        print(f"staged database -> {dump_staged(args.out)}")


if __name__ == "__main__":
    main()
