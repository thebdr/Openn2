#!/usr/bin/env python3
"""run.py - one command for the whole safety-DB pipeline.

    documents -> staging -> validation -> outputs

Reads the customer I/O List + Cause&Effect matrix (paths in config/params.json)
and writes, under the output dir (default DatabaseTool/Output):

    validation_log.txt        C&E / AREA cross-check vs the I/O List
    IoTags/<ScriptType>.csv    one tag table per signal type
    DBs/<name>.db              SCL data blocks (std / fail-safe)
    Diagnosis/List_IO.csv      diagnosis-relevant points
    Hardware/Stations.csv      format-2 hardware config for Openn2
    Hardware/Modules.csv
    Interfaces/IF_<inst>.xlsx   per-machine interface tables (IOC rows)

Paths resolve relative to this file, so it runs from any working directory
(the repo has a sibling clone - always run THIS copy explicitly).

Exit code: 0 on success; 1 if a hardware ERROR occurred (a device with no
DeviceTypesDatabase entry, so it could not be generated) or, with --strict,
if any validation check FAILed; 2 if a required source document is missing.

Usage:
    python run.py [--params config/params.json] [--out DIR] [--strict]
"""
from __future__ import annotations
import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from safetydb import config, staging, validation, outputs, hardware
import interface_tool


def _abs(path: str) -> str:
    """Resolve a config path relative to DatabaseTool/ unless already absolute."""
    return path if os.path.isabs(path) else os.path.normpath(os.path.join(_HERE, path))


def _section(title: str) -> None:
    print("\n" + "=" * 72 + f"\n{title}\n" + "=" * 72)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Run the full safety-DB pipeline: documents -> staging -> validation -> outputs.")
    ap.add_argument("--params", default=None, help="path to params.json (default: config/params.json)")
    ap.add_argument("--out", default=None, help="output dir (default: params.output_dir under DatabaseTool/)")
    ap.add_argument("--strict", action="store_true",
                    help="exit non-zero if any validation check FAILs (default: only on hardware ERROR)")
    args = ap.parse_args(argv)

    params = config.load_params(args.params)
    out_dir = _abs(args.out or params.get("output_dir", "Output"))
    io_path = params["io_list"]["path"]

    if not os.path.exists(io_path):
        print(f"ERROR: I/O List not found: {io_path}", file=sys.stderr)
        return 2

    types = config.load_signal_types()
    dtd = config.load_device_types_db(params)
    print(f"output dir: {out_dir}")

    # ---- staging -------------------------------------------------------
    _section("STAGING  (reading the I/O List)")
    rows, warnings = staging.load_io_list(params, types)
    print(f"  {len(rows)} row(s) loaded")
    for w in warnings:
        print(f"  - {w}")

    # ---- validation ----------------------------------------------------
    _section("VALIDATION  (C&E / AREA vs I/O List)")
    failed = 0
    if os.path.exists(params["ce"]["path"]):
        log = validation.validate(params, rows)
        passed, failed = validation.write_log(log, out_dir)
        print(f"  {passed} passed, {failed} failed  ->  {os.path.join(out_dir, 'validation_log.txt')}")
        for e in log:
            if e.level == "FAIL":
                print(f"  FAIL {e.location}: {e.message}")
    else:
        print(f"  C&E document not found ({params['ce']['path']}) - skipped")

    # ---- I/O tags ------------------------------------------------------
    _section("I/O TAGS")
    tables = outputs.build_io_tags(rows)
    n_tags = outputs.write_io_tags(tables, out_dir)
    print(f"  {n_tags} tag(s) across {len(tables)} table(s) -> {os.path.join(out_dir, 'IoTags', 'PLCTags.xlsx')}")

    # ---- data blocks ---------------------------------------------------
    _section("DATA BLOCKS")
    dbs = outputs.build_dbs(rows, types)
    n_dbs = outputs.write_dbs(dbs, out_dir)
    print(f"  {n_dbs} DB(s) -> {os.path.join(out_dir, 'DBs')}")
    for name, db in sorted(dbs.items()):
        kind = "safe" if db["kind"] == "safe_db" else "std"
        print(f"  - {name}  ({kind}, {len(db['members'])} member(s))")

    # ---- diagnosis -----------------------------------------------------
    _section("DIAGNOSIS  (List_IO + List_Logic + OPC SCL)")
    import diagnostic_opc
    d = diagnostic_opc.generate_for(rows, params, out_dir)
    print(f"  {d['io']} List_IO + {d['logic']} List_Logic row(s) -> Diagnosis/")
    print(f"  SCL -> {os.path.relpath(d['scl'], out_dir)}")

    # ---- hardware ------------------------------------------------------
    _section("HARDWARE  (Stations / Modules, format 2)")
    stations, modules, messages = hardware.extract(rows, dtd)
    n_st = hardware.write_stations(stations, out_dir)
    n_mod = hardware.write_modules(modules, out_dir)
    print(f"  {n_st} station(s), {n_mod} module(s) -> {os.path.join(out_dir, 'Hardware')}")
    hw_errors = sum(1 for level, _ in messages if level == "ERROR")
    for level, text in messages:
        print(f"  {level}: {text}")

    # ---- interfaces ----------------------------------------------------
    _section("INTERFACES  (IOC rows)")
    tpl = _abs(params.get("interface_template", "Templates/TEMPLATE_INTERFACES_v0.0.xlsx"))
    n_if = 0
    if os.path.exists(tpl):
        if_dir = os.path.join(out_dir, "Interfaces")
        n_if = interface_tool.generate(io_path, params["io_list"]["sheet"],
                                       params["io_list"]["header_row"], if_dir, tpl)
        print(f"  {n_if} file(s) created (existing preserved) -> {if_dir}")
    else:
        print(f"  interface template not found ({tpl}) - skipped")

    # ---- coverage ------------------------------------------------------
    _section("COVERAGE  (every signal lands somewhere)")
    cov = {"covered": 0, "total": len(rows), "orphans": 0, "unplaced": 0, "untyped": 0}
    try:
        import verify  # lazy: a half-written block_builders.py must not break the run
        records, findings, counts = verify.compute_coverage(rows)
        report_dir = os.path.join(out_dir, "Report")
        verify.write_csv(records, report_dir)
        _txt, cov = verify.write_txt(records, findings, counts, report_dir)
        print(f"  {cov['covered']}/{cov['total']} covered, {cov['orphans']} orphan(s), "
              f"{cov['unplaced']} unplaced member(s), {cov['untyped']} untyped/spare  ->  {report_dir}")
    except Exception as e:  # noqa: BLE001
        print(f"  coverage skipped: {e}")

    # ---- summary -------------------------------------------------------
    _section("SUMMARY")
    print(f"  rows staged    : {len(rows)}")
    print(f"  validation     : {failed} fail(s)")
    print(f"  I/O tags / DBs : {n_tags} / {n_dbs}")
    print(f"  diagnosis      : {d['io']} List_IO + {d['logic']} List_Logic + OPC SCL")
    print(f"  hardware       : {n_st} station(s), {n_mod} module(s), {hw_errors} error(s)")
    print(f"  interfaces     : {n_if} created")
    print(f"  coverage       : {cov['covered']}/{cov['total']} covered, {cov['orphans']} orphan(s), "
          f"{cov['unplaced']} unplaced")

    rc = 0
    if hw_errors:
        print(f"  -> exit 1: {hw_errors} hardware ERROR(s) (device(s) not in DeviceTypesDatabase)")
        rc = 1
    if args.strict and failed:
        print(f"  -> exit 1: {failed} validation failure(s) (--strict)")
        rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
