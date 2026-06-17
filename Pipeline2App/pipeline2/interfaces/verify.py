#!/usr/bin/env python3
"""verify.py — coverage check + report (tooling, not the pipeline).

For every CentralDatabase row, mark which outputs it lands in and report the gaps:

  io_tag      outputs._is_io_signal (resolved non-interface type with an I/Q bit)
  db          name_in_db != ''  (it is a DB member)
  diagnosis   its type is in_diagnosis
  interface   its type's category is Interface (IOC)
  hardware    hardware._role is not None (Plc / PlcCardCm / IoDevice head)
  block       its name_in_db is emitted by some builder - an ITERATOR element or a
              scalar `…_memberOf:` slot (block_builders)

  ORPHAN          - a row in NONE of the above              (WARNING)
  UNPLACED MEMBER - a DB member not referenced by any block (WARNING; a worklist
                    for completing block_builders.py)

Writes Reports/io_project_coverage_report.csv (one row per signal) + io_project_coverage_report.txt (findings).

  python -m pipeline2.interfaces.verify [--out DIR]
"""
from __future__ import annotations
import argparse
import csv
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP_ROOT = os.path.dirname(os.path.dirname(_HERE))   # Pipeline2App (so `pipeline2` resolves
if _APP_ROOT not in sys.path:                         # when a submodule is run directly)
    sys.path.insert(0, _APP_ROOT)

from pipeline2.core import config, staging, outputs, hardware
from pipeline2.blocks import block_builders

DEST = ["io_tag", "db", "diagnosis", "interface", "hardware", "block"]
CSV_COLS = (["_source_sheet", "_source_row", "script_type", "functional_unit", "location",
             "device", "name_in_db", "matrix_areas"] + DEST + ["covered", "finding"])


def _abs(path: str) -> str:
    return path if os.path.isabs(path) else os.path.normpath(os.path.join(_HERE, path))


_CONTROL_KEYS = ("_pad", "_sizes", "_template_type")


def _block_placed(db: list) -> set:
    """Every string a builder emits - ITERATOR lists AND scalar slots (e.g. the
    `…_memberOf:` keys of 04/05/08) - so a member placed in a fixed slot still counts."""
    placed = set()
    for builder in block_builders.BUILDERS.values():
        try:
            for inst in builder(db):
                for k, v in inst.items():
                    if k in _CONTROL_KEYS:
                        continue
                    if isinstance(v, list):
                        placed.update(str(x) for x in v)
                    elif v:
                        placed.add(str(v))
        except Exception:  # noqa: BLE001 - a half-written builder must not break the report
            pass
    return placed


def _fld(r) -> str:
    return (str(r.get("functional_unit", "")) + str(r.get("location", "")) + str(r.get("device", "")))


def compute_coverage(db: list) -> tuple[list, list, dict]:
    """Returns (records, findings, counts).
    record  = dict with CSV_COLS; finding = (level, kind, ref, message)."""
    placed = _block_placed(db)
    records, findings = [], []
    counts = {c: 0 for c in DEST}

    for r in db:
        t = r.get("_type") or {}
        nid = r.get("name_in_db", "")
        dest = {
            "io_tag": bool(outputs._is_io_signal(r)),
            "db": bool(nid),
            "diagnosis": bool(t.get("in_diagnosis")),
            "interface": t.get("category") == "Interface",
            "hardware": hardware._role(r) is not None,
            "block": bool(nid) and nid in placed,
        }
        for c in DEST:
            counts[c] += int(dest[c])
        covered = any(dest.values())
        script = str(r.get("script_type", "")).strip()
        ref = f"{r.get('_source_sheet', '')}:{r.get('_source_row', '')}"

        finding = ""
        if not covered:
            # only a row that carries a Script Type is an intended signal; an
            # uncovered row with no Script Type is a spare/unused channel (not an orphan).
            if script:
                finding = "ORPHAN"
                findings.append(("WARNING", "ORPHAN", ref,
                                 f"{script} {_fld(r)} — typed but in no output"))
            else:
                finding = "untyped"
        elif nid and not dest["block"]:
            finding = "UNPLACED"
            findings.append(("WARNING", "UNPLACED", ref,
                             f"{nid} (db member) not in any software block"))

        rec = {k: r.get(k, "") for k in CSV_COLS if k in r}
        rec.update({k: ("yes" if dest[k] else "") for k in DEST})
        rec["covered"] = "yes" if covered else ""
        rec["finding"] = finding
        records.append(rec)

    return records, findings, counts


def write_csv(records: list, out_dir: str) -> str:
    path = config.out_path(out_dir, "coverage_report") + ".csv"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(CSV_COLS)
        for rec in records:
            w.writerow([rec.get(c, "") for c in CSV_COLS])
    return path


def write_txt(records: list, findings: list, counts: dict, out_dir: str) -> tuple[str, dict]:
    path = config.out_path(out_dir, "coverage_report") + ".txt"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    orphans = [f for f in findings if f[1] == "ORPHAN"]
    unplaced = [f for f in findings if f[1] == "UNPLACED"]
    errors = sum(1 for f in findings if f[0] == "ERROR")
    covered = sum(1 for r in records if r["covered"])
    untyped = sum(1 for r in records if r["finding"] == "untyped")
    with open(path, "w", encoding="utf-8") as f:
        f.write("COVERAGE REPORT\n")
        f.write(f"  CentralDatabase rows: {len(records)}  (covered {covered}, "
                f"untyped/spare {untyped})\n")
        f.write("  " + "   ".join(f"{c}={counts[c]}" for c in DEST) + "\n\n")
        f.write(f"ORPHANS (typed, but in no output) — {len(orphans)}:\n")
        for lvl, _kind, ref, msg in orphans:
            f.write(f"  [{lvl}] {ref}  {msg}\n")
        f.write(f"\nUNPLACED DB MEMBERS (not in any software block) — {len(unplaced)}:\n")
        for lvl, _kind, ref, msg in unplaced:
            f.write(f"  [{lvl}] {ref}  {msg}\n")
        f.write(f"\nSUMMARY: {covered} covered, {len(orphans)} orphan(s), "
                f"{len(unplaced)} unplaced member(s), {untyped} untyped/spare\n")
    return path, {"orphans": len(orphans), "unplaced": len(unplaced), "errors": errors,
                  "untyped": untyped, "covered": covered, "total": len(records)}


def generate(out_dir: str | None = None, params_path: str | None = None) -> dict:
    params = config.load_params(params_path)
    types = config.load_signal_types()
    db, _warnings = staging.load_io_list(params, types)
    out_dir = out_dir or config.output_root(params)
    records, findings, counts = compute_coverage(db)
    csv_path = write_csv(records, out_dir)
    txt_path, summary = write_txt(records, findings, counts, out_dir)
    summary.update({"csv": csv_path, "txt": txt_path, "counts": counts})
    return summary


def main():
    ap = argparse.ArgumentParser(description="Coverage check + report (every signal lands somewhere).")
    ap.add_argument("--out", default=None, help="output dir (default: Reports/ under the output tree)")
    args = ap.parse_args()
    s = generate(args.out)
    print(f"coverage: {s['covered']}/{s['total']} covered, {s['orphans']} orphan(s), "
          f"{s['unplaced']} unplaced member(s), {s['untyped']} untyped/spare")
    print("  " + "   ".join(f"{c}={s['counts'][c]}" for c in DEST))
    print(f"  -> {s['csv']}\n  -> {s['txt']}")
    raise SystemExit(1 if s["errors"] else 0)


if __name__ == "__main__":
    main()
