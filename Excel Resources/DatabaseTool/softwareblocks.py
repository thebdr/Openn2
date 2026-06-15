#!/usr/bin/env python3
"""softwareblocks.py — generate the SoftwareBlocksBuilder CSV(s) from block_builders.

Loads the CentralDatabase (staging), calls each registered builder, and writes one
CSV per template in the SoftwareBlocksBuilder format:

  $  template=...                 directive (the .xml template)
  #  comment
  %  TemplateType,#Templates Capacity,#Templates Index,#Elements Needed,!!key$$...
  @  one block instance: TemplateType + #Elements Needed + the key values; the
     ITERATOR (the list-valued key) expands rightward, padded to the chosen
     capacity with the instance's pad value.

#Elements Needed = the real element count; TemplateType = the Index of the smallest
Capacity >= that count, from the template's sidecar capacity CSV (rides along in cols
C/D for reference). Not part of the pipeline.

  python softwareblocks.py [--out DIR]
"""
from __future__ import annotations
import argparse
import csv
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from safetydb import config, staging
import block_builders
import block_templates

TEMPLATES_DIR = os.path.join(_HERE, "Templates", "Tia Portal Software Blocks")
META_COLS = ["TemplateType", "#Templates Capacity", "#Templates Index", "#Elements Needed"]
TEMPLATE_PATH_PREFIX = r"\XML Templates"   # how the $ directive references the template


def _abs(path: str) -> str:
    return path if os.path.isabs(path) else os.path.normpath(os.path.join(_HERE, path))


def _load_capacity(stem: str) -> list:
    """Sidecar capacity CSV (same name as the template) -> sorted [(capacity, index)]."""
    path = os.path.join(TEMPLATES_DIR, stem + ".csv")
    table = []
    if os.path.exists(path):
        with open(path, newline="", encoding="utf-8-sig") as f:
            for r in csv.reader(f):
                if len(r) >= 2 and str(r[0]).strip().isdigit() and str(r[1]).strip().isdigit():
                    table.append((int(r[0]), int(r[1])))
    return sorted(table)


def _pick(table: list, n: int):
    """Smallest (capacity, index) with capacity >= n; the largest tier if none fits;
    (n, '') when there is no table (no sizing -> no padding)."""
    if not table:
        return n, ""
    for cap, idx in table:
        if cap >= n:
            return cap, idx
    return table[-1]


def _load_capacity_multi(stem: str):
    """Multi-family sidecar (>1 '#Templates Capacity <family>' column): returns
    (families, [((cap, cap, ...), index), ...]); (None, None) for a single-capacity or
    purpose sidecar (handled by _load_capacity)."""
    path = os.path.join(TEMPLATES_DIR, stem + ".csv")
    if not os.path.exists(path):
        return None, None
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    if not rows:
        return None, None
    header = [c.strip() for c in rows[0]]
    cap_cols = [i for i, h in enumerate(header) if h.startswith("#Templates Capacity")]
    idx_col = next((i for i, h in enumerate(header) if h.startswith("#Templates Index")), None)
    if len(cap_cols) < 2 or idx_col is None:
        return None, None
    families = [header[i].replace("#Templates Capacity", "").strip() for i in cap_cols]
    table = []
    for r in rows[1:]:
        if (all(i < len(r) and str(r[i]).strip().isdigit() for i in cap_cols)
                and idx_col < len(r) and str(r[idx_col]).strip().isdigit()):
            table.append((tuple(int(r[i]) for i in cap_cols), int(r[idx_col])))
    return families, table


def _pick_multi(families: list, table: list, sizes: dict):
    """The Index of the smallest variant whose every family capacity >= that family's
    count (sizes = {family: count}); tie-break by smaller Index. Largest tier if none
    fits; '' if no table."""
    if not table:
        return ""
    want = [sizes.get(f, 0) for f in families]
    fits = [(caps, idx) for caps, idx in table if all(c >= w for c, w in zip(caps, want))]
    if not fits:
        return max(table, key=lambda ci: (sum(ci[0]), ci[1]))[1]
    return min(fits, key=lambda ci: (sum(ci[0]), ci[1]))[1]


def _instance_keys(instances: list, stem: str) -> list:
    """Union of the instances' key names (first-seen order, control keys dropped);
    falls back to scanning the template when the builder produced nothing."""
    keys = []
    for inst in instances:
        for k in inst:
            if k not in ("_pad", "_sizes", "_template_type") and k not in keys:
                keys.append(k)
    return keys or block_templates.scan_template_keys().get(stem, [])


def _build_multi(stem: str, builder, db: list, families: list, table: list) -> tuple:
    """Multi-family templates (e.g. 05): fixed numbered slots, no ITERATOR. TemplateType
    comes from matching the instance's per-family counts (its '_sizes') to the sidecar."""
    instances = builder(db)
    keys = _instance_keys(instances, stem)
    meta = ["TemplateType"] + [f"#Templates Capacity {f}" for f in families] + ["#Templates Index", "#Elements Needed"]
    nlead = 1 + len(meta)          # marker + meta columns
    ncap = len(families)

    data_rows = []
    for inst in instances:
        sizes = inst.get("_sizes", {})
        idx = _pick_multi(families, table, sizes)
        tt = f"{idx:02d}" if isinstance(idx, int) else str(idx)
        elem = "|".join(str(sizes.get(f, "")) for f in families)   # per-family counts
        data_rows.append((tt, elem, [str(inst.get(k, "")) for k in keys]))

    grid = [["$", f"template={TEMPLATE_PATH_PREFIX}\\{stem}.xml"],
            ["#", "generated by softwareblocks.py"],
            ["%"] + meta + [f"!!{k}$$" for k in keys] + ["# ----->"]]
    for i in range(max(len(data_rows), len(table))):
        cell = [""] * nlead
        tail = []
        if i < len(data_rows):
            tt, elem, scal = data_rows[i]
            cell[0], cell[1], cell[nlead - 1] = "@", tt, elem
            tail = scal
        if i < len(table):                       # the sidecar rides alongside (caps + index)
            caps, idx = table[i]
            for j, c in enumerate(caps):
                cell[2 + j] = str(c)
            cell[2 + ncap] = str(idx)
        grid.append(cell + tail)
    width = max(len(r) for r in grid)
    return [r + [""] * (width - len(r)) for r in grid], len(data_rows)


def build_template_csv(stem: str, builder, db: list) -> list:
    """Return the CSV grid (list of rows) for one template."""
    families, multi_table = _load_capacity_multi(stem)
    if families:
        return _build_multi(stem, builder, db, families, multi_table)
    table = _load_capacity(stem)
    instances = builder(db)
    # column keys = the union of the builders' instance keys (first-seen order); if the
    # builder produced nothing, fall back to scanning the template (no json needed).
    keys = _instance_keys(instances, stem)

    # the iterator key = the one that carries a list value
    iter_key = next((k for inst in instances for k, v in inst.items() if isinstance(v, list)), None)
    # the ITERATOR column is always the LAST !!key$$; key it by the list value when there are
    # instances, else by name (so the shell, built from empty instances, still puts it last)
    last_key = iter_key or ("ITERATOR_STRINGS" if "ITERATOR_STRINGS" in keys else None)
    scalar_keys = [k for k in keys if k != last_key]
    ordered_keys = scalar_keys + ([last_key] if last_key else [])

    data_rows = []  # (template_type, n_elements, [scalar cells], [iterator cells])
    for inst in instances:
        items = list(inst.get(iter_key, [])) if iter_key else []
        n = len(items)
        cap, idx = _pick(table, n)
        idx = inst.get("_template_type", idx)   # a builder may set TemplateType directly (e.g. 08 per purpose)
        pad = inst.get("_pad", block_builders.PAD)
        padded = items + [pad] * max(0, cap - n) if isinstance(cap, int) else items
        scal = [str(inst.get(k, "")) for k in scalar_keys]
        data_rows.append((idx, n, scal, padded))

    grid = []
    grid.append(["$", f"template={TEMPLATE_PATH_PREFIX}\\{stem}.xml"])
    grid.append(["#", "generated by softwareblocks.py"])
    grid.append(["%"] + META_COLS + [f"!!{k}$$" for k in ordered_keys] + ["# ----->"])

    for i in range(max(len(data_rows), len(table))):
        cell = ["", "", "", "", ""]  # marker, TemplateType, Capacity, Index, ElementsNeeded
        tail = []
        if i < len(data_rows):
            idx, n, scal, padded = data_rows[i]
            template_type = f"{idx:02d}" if isinstance(idx, int) else str(idx)
            cell[0], cell[1], cell[4] = "@", template_type, str(n)
            tail = scal + padded
        if i < len(table):
            cell[2], cell[3] = str(table[i][0]), str(table[i][1])
        grid.append(cell + tail)

    width = max(len(r) for r in grid)
    return [r + [""] * (width - len(r)) for r in grid], len(data_rows)


def generate(out_dir: str | None = None, params_path: str | None = None,
             shell_path: str | None = None) -> dict:
    import blockshells  # lazy: avoid an import cycle
    params = config.load_params(params_path)
    types = config.load_signal_types()
    db, _warnings = staging.load_io_list(params, types)   # CentralDatabase (has all builder columns)
    out_dir = out_dir or os.path.join(_abs(params.get("output_dir", "Output")), "SoftwareBlocks")
    os.makedirs(out_dir, exist_ok=True)
    shell = shell_path or blockshells.shell_path(params)
    mode_of = blockshells.modes(shell)   # {stem -> keep|fill|override}

    written = {}
    for stem, builder in block_builders.BUILDERS.items():
        mode = mode_of.get(stem, "keep")
        if mode == "override":                       # take the @ rows straight from the sheet
            grid = blockshells.override_grid(stem, shell)
            n = sum(1 for r in grid if r and r[0] == "@")
        else:
            grid, n = build_template_csv(stem, builder, db)
            if mode == "fill":                       # build, then mirror the @ rows into the sheet
                blockshells.write_fill(stem, grid, shell)
        path = os.path.join(out_dir, stem + ".csv")
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            csv.writer(f, lineterminator="\n").writerows(grid)
        written[stem] = (path, n, mode)
    return written


def main():
    ap = argparse.ArgumentParser(description="Generate SoftwareBlocksBuilder CSVs from block_builders.py")
    ap.add_argument("--out", default=None, help="output dir (default Output/SoftwareBlocks)")
    args = ap.parse_args()
    for stem, (path, n, mode) in generate(args.out).items():
        print(f"{n:3} instance(s)  [{mode}]  ->  {path}")


if __name__ == "__main__":
    main()
