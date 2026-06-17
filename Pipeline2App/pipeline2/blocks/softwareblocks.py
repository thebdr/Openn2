#!/usr/bin/env python3
"""softwareblocks.py — generate the SoftwareBlocksBuilder CSV(s) from block_builders.

Loads the CentralDatabase (staging), calls each registered builder, and writes one
CSV per template in the SoftwareBlocksBuilder format:

  $  template=...                 directive (the .xml template)
  #  comment
  %  TemplateType,<sidecar meta columns>,!!key$$...
  @  one block instance: TemplateType + the meta values + the key values; the
     ITERATOR (the list-valued key) expands rightward, padded to the chosen
     capacity (for capacity sidecars) with the instance's pad value.

The meta columns after TemplateType are derived from the template's sidecar CSV:
  * no sidecar / purpose sidecar    -> just TemplateType
  * capacity sidecar (single/multi) -> + #Templates Capacity.../#Templates Index/#Elements Needed
  * doors sidecar (machine type)    -> + the sidecar's header columns, verbatim
The sidecar table rides alongside the @ data (cols mirror the sidecar). Output files
drop the template's "TEMPLATE--vX.Y--" filename prefix (e.g. 07_Speed Control.csv).

  python softwareblocks.py [--out DIR]
"""
from __future__ import annotations
import argparse
import csv
import glob
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP_ROOT = os.path.dirname(os.path.dirname(_HERE))   # Pipeline2App (so `pipeline2` resolves
if _APP_ROOT not in sys.path:                         # when a submodule is run directly)
    sys.path.insert(0, _APP_ROOT)

from pipeline2.core import config, staging
from pipeline2.blocks import block_builders
from pipeline2.blocks import block_templates

TEMPLATES_DIR = config.BLOCK_TEMPLATES_DIR
TEMPLATE_PATH_PREFIX = r"\XML Templates"   # how the $ directive references the template
# generated output CSVs drop the template's "TEMPLATE--vX.Y--" filename prefix
_OUT_PREFIX_RE = re.compile(r"^TEMPLATE--v\d+\.\d+--")


def _abs(path: str) -> str:
    return path if os.path.isabs(path) else os.path.normpath(os.path.join(_HERE, path))


def _pick(table: list, n: int):
    """Smallest (capacity, index) with capacity >= n; the largest tier if none fits;
    (n, '') when there is no table (no sizing -> no padding)."""
    if not table:
        return n, ""
    for cap, idx in table:
        if cap >= n:
            return cap, idx
    return table[-1]


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


def _read_sidecar_rows(stem: str):
    """The non-empty rows of the template's sidecar CSV (same stem), or None."""
    path = os.path.join(TEMPLATES_DIR, stem + ".csv")
    if not os.path.exists(path):
        return None
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = [r for r in csv.reader(f) if any(str(c).strip() for c in r)]
    return rows or None


def _load_sidecar(stem: str) -> dict:
    """Inspect the template's sidecar CSV and describe its layout:
      kind   - 'none' | 'purpose' | 'capacity' | 'multi' | 'doors'
      meta   - the meta column headers that follow 'TemplateType' in the % header
      ride   - rows of values (for the non-'#Elements Needed' meta columns) that ride
               alongside the @ data, mirroring the sidecar table
      sizing - kind-specific table used to pick TemplateType ('capacity'/'multi'/'doors')
    """
    rows = _read_sidecar_rows(stem)
    if not rows:
        return {"kind": "none", "meta": [], "ride": [], "sizing": None}
    header = [c.strip() for c in rows[0]]
    body = rows[1:]
    cap_cols = [i for i, h in enumerate(header) if h.startswith("#Templates Capacity")]
    idx_col = next((i for i, h in enumerate(header) if h.startswith("#Templates Index")), None)

    # purpose sidecar (e.g. 08): the builder sets TemplateType; nothing rides
    if any(h.startswith("#Templates Purpose") for h in header):
        return {"kind": "purpose", "meta": [], "ride": [], "sizing": None}

    # doors sidecar (e.g. 04): machine-type / door-capacity layout, emitted + ridden verbatim
    if any(h.startswith("#Templates Machine Type") or h.startswith("#Templates Capacity Doors")
           for h in header):
        cols = [i for i, h in enumerate(header) if h.startswith("#Templates")]
        meta = [header[i] for i in cols]
        ride = [[r[i] if i < len(r) else "" for i in cols] for r in body]
        dc_col = next((i for i, h in enumerate(header)
                       if h.startswith("#Templates Capacity Doors")), None)
        sizing = []
        if dc_col is not None and idx_col is not None:
            for r in body:
                if (dc_col < len(r) and str(r[dc_col]).strip().isdigit()
                        and idx_col < len(r) and str(r[idx_col]).strip().isdigit()):
                    sizing.append((int(r[dc_col]), int(r[idx_col])))
        return {"kind": "doors", "meta": meta, "ride": ride, "sizing": sorted(sizing)}

    # multi-family capacity sidecar (e.g. 05): >1 '#Templates Capacity <family>' column
    if len(cap_cols) >= 2 and idx_col is not None:
        families = [header[i].replace("#Templates Capacity", "").strip() for i in cap_cols]
        table, ride = [], []
        for r in body:
            if (all(i < len(r) and str(r[i]).strip().isdigit() for i in cap_cols)
                    and idx_col < len(r) and str(r[idx_col]).strip().isdigit()):
                caps = tuple(int(r[i]) for i in cap_cols)
                idx = int(r[idx_col])
                table.append((caps, idx))
                ride.append([str(c) for c in caps] + [str(idx)])
        meta = ([f"#Templates Capacity {f}" for f in families]
                + ["#Templates Index", "#Elements Needed"])
        return {"kind": "multi", "meta": meta, "ride": ride, "sizing": (families, table)}

    # single-capacity sidecar (e.g. 02, 03, 06)
    if cap_cols and idx_col is not None:
        table, ride = [], []
        for r in body:
            if (cap_cols[0] < len(r) and str(r[cap_cols[0]]).strip().isdigit()
                    and idx_col < len(r) and str(r[idx_col]).strip().isdigit()):
                cap, idx = int(r[cap_cols[0]]), int(r[idx_col])
                table.append((cap, idx))
                ride.append([str(cap), str(idx)])
        meta = ["#Templates Capacity", "#Templates Index", "#Elements Needed"]
        return {"kind": "capacity", "meta": meta, "ride": ride, "sizing": sorted(table)}

    return {"kind": "none", "meta": [], "ride": [], "sizing": None}


def _ordered_keys(instances: list, keys: list):
    """(iter_key, scalar_keys, ordered_keys): the ITERATOR (the list-valued key, else the
    'ITERATOR_STRINGS' key) is placed last; everything else keeps first-seen order."""
    iter_key = next((k for inst in instances for k, v in inst.items() if isinstance(v, list)), None)
    last_key = iter_key or ("ITERATOR_STRINGS" if "ITERATOR_STRINGS" in keys else None)
    scalar_keys = [k for k in keys if k != last_key]
    return iter_key, scalar_keys, scalar_keys + ([last_key] if last_key else [])


def _pad_grid(grid: list) -> list:
    width = max(len(r) for r in grid)
    return [r + [""] * (width - len(r)) for r in grid]


def build_template_csv(stem: str, builder, db: list) -> tuple:
    """Return (CSV grid, instance count) for one template. The % header is
    'TemplateType' + the sidecar-derived meta columns + the template's !!key$$ columns;
    @ rows carry TemplateType + the meta values + the key values (the ITERATOR padded to
    the chosen capacity for capacity sidecars). The sidecar table rides alongside."""
    sc = _load_sidecar(stem)
    instances = builder(db)
    keys = _instance_keys(instances, stem)
    iter_key, scalar_keys, ordered_keys = _ordered_keys(instances, keys)

    grid = [["$", f"template={TEMPLATE_PATH_PREFIX}\\{stem}.xml"],
            ["#", "generated by softwareblocks.py"],
            ["%", "TemplateType"] + sc["meta"] + [f"!!{k}$$" for k in ordered_keys] + ["# ----->"]]

    # vertical: a list-iterator template with no sizing sidecar -> one row per element (e.g. 00)
    if sc["kind"] == "none" and iter_key is not None:
        n_inst = 0
        for inst in instances:
            n_inst += 1
            tt = inst.get("_template_type", 1)
            tt = f"{tt:02d}" if isinstance(tt, int) else str(tt)
            scal = [str(inst.get(k, "")) for k in scalar_keys]
            items = list(inst.get(iter_key, []))
            for j, item in enumerate(items):
                lead = (["@", tt] if j == 0 else ["", tt])
                body = (scal if j == 0 else [""] * len(scal)) + [str(item)]
                grid.append(lead + body)
        return _pad_grid(grid), n_inst

    # general path (capacity / multi / doors / purpose / scalar-only no-sidecar)
    meta = sc["meta"]
    elem_pos = meta.index("#Elements Needed") if "#Elements Needed" in meta else None
    n_lead = 2 + len(meta)                         # marker + TemplateType + meta extras
    pad_iter = sc["kind"] in ("capacity", "multi")

    data_rows = []
    for inst in instances:
        items = list(inst.get(iter_key, [])) if iter_key else []
        n = len(items)
        cap = None
        if sc["kind"] == "capacity":
            cap, idx = _pick(sc["sizing"], n)
        elif sc["kind"] == "multi":
            families, table = sc["sizing"]
            idx = _pick_multi(families, table, inst.get("_sizes", {}))
        else:
            idx = ""
        idx = inst.get("_template_type", idx)
        if idx == "" or idx is None:
            idx = 1
        tt = f"{idx:02d}" if isinstance(idx, int) else str(idx)
        pad = inst.get("_pad", block_builders.PAD)
        tail_iter = items + [pad] * max(0, cap - n) if (pad_iter and isinstance(cap, int)) else items
        scal = [str(inst.get(k, "")) for k in scalar_keys]
        elem = ("|".join(str(inst.get("_sizes", {}).get(f, "")) for f in sc["sizing"][0])
                if sc["kind"] == "multi" else str(n))
        data_rows.append((tt, elem, scal + tail_iter))

    ride = sc["ride"]
    for i in range(max(len(data_rows), len(ride))):
        cell = [""] * n_lead
        tail = []
        if i < len(data_rows):
            tt, elem, tail = data_rows[i]
            cell[0], cell[1] = "@", tt
            if elem_pos is not None:
                cell[2 + elem_pos] = elem
        if i < len(ride):
            k = 0
            for mpos, mhdr in enumerate(meta):
                if mhdr == "#Elements Needed":
                    continue
                if k < len(ride[i]):
                    cell[2 + mpos] = ride[i][k]
                k += 1
        grid.append(cell + tail)
    return _pad_grid(grid), len(data_rows)


def _out_name(stem: str) -> str:
    """Output CSV filename: the template stem with its 'TEMPLATE--vX.Y--' prefix dropped."""
    return _OUT_PREFIX_RE.sub("", stem) + ".csv"


_INSTANCE_OF = "!!instanceOf-"   # placeholder prefix marking an FB instance column


def _instance_db_rows(grid: list) -> list:
    """[(name, instance_of)] from a built block grid: every non-empty @-row value under an
    `!!instanceOf-<FB>$$` column (instance_of = <FB>, the text after 'instanceOf-')."""
    header = next((r for r in grid if r and r[0] == "%"), None)
    if not header:
        return []
    cols = {i: c[len(_INSTANCE_OF):-2] for i, c in enumerate(header)
            if isinstance(c, str) and c.startswith(_INSTANCE_OF) and c.endswith("$$")}
    out = []
    for r in grid:
        if r and r[0] == "@":
            for i, fb in cols.items():
                name = (r[i] or "").strip() if i < len(r) else ""
                if name:
                    out.append((name, fb))
    return out


def write_instance_dbs(rows: list, out_dir: str) -> tuple:
    """Write the CreateInstanceDB list (SoftwareBlocks/CreationInfo/InstanceDBs.csv): one row per
    FB instance -> Name, InstanceOf (the FB), Number (blank, TIA auto), Folder (the FB)."""
    path = os.path.join(out_dir, "InstanceDBs.csv")
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["#", "Instance DBs created directly via CreateInstanceDB"])
        w.writerow(["%", "Name", "InstanceOf", "Number", "Folder"])
        for name, fb in rows:
            w.writerow(["@", name, fb, "", fb])
    return path, len(rows)


def generate(out_dir: str | None = None, params_path: str | None = None,
             shell_path: str | None = None) -> dict:
    from pipeline2.blocks import blockshells  # lazy: avoid an import cycle
    params = config.load_params(params_path)
    types = config.load_signal_types()
    db, _warnings = staging.load_io_list(params, types)   # CentralDatabase (has all builder columns)
    out_dir = out_dir or config.out_path(config.output_root(params), "blocks_creation_dir")
    os.makedirs(out_dir, exist_ok=True)
    for old in glob.glob(os.path.join(out_dir, "TEMPLATE--v*.csv")):   # drop pre-rename outputs
        try:
            os.remove(old)
        except OSError:
            pass
    shell = shell_path or blockshells.shell_path(params)
    mode_of = blockshells.modes(shell)   # {stem -> keep|fill|override}

    written = {}
    inst_rows, seen = [], set()
    for stem, builder in block_builders.BUILDERS.items():
        mode = mode_of.get(stem, "keep")
        if mode == "override":                       # take the @ rows straight from the sheet
            grid = blockshells.override_grid(stem, shell)
            n = sum(1 for r in grid if r and r[0] == "@")
        else:
            grid, n = build_template_csv(stem, builder, db)
            if mode == "fill":                       # build, then mirror the @ rows into the sheet
                blockshells.write_fill(stem, grid, shell)
        path = os.path.join(out_dir, _out_name(stem))
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            csv.writer(f, lineterminator="\n").writerows(grid)
        written[stem] = (path, n, mode)
        for name, fb in _instance_db_rows(grid):     # collect FB instances for CreateInstanceDB
            if name not in seen:
                seen.add(name)
                inst_rows.append((name, fb))

    ipath, icount = write_instance_dbs(inst_rows, out_dir)
    written["InstanceDBs"] = (ipath, icount, "list")
    return written


def main():
    ap = argparse.ArgumentParser(description="Generate SoftwareBlocksBuilder CSVs from block_builders.py")
    ap.add_argument("--out", default=None, help="output dir (default: SoftwareBlocks/CreationInfo under the output tree)")
    args = ap.parse_args()
    for stem, (path, n, mode) in generate(args.out).items():
        print(f"{n:3} instance(s)  [{mode}]  ->  {path}")


if __name__ == "__main__":
    main()
