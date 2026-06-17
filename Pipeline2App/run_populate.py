#!/usr/bin/env python3
"""run_populate.py - the I/O-list diagnosis populator as a standalone command.

Runs only the populate stage (the same one run.py invokes before staging): fills script_type /
index / diag_cabinet / diag_bit, (re)generates the DiagnosisBlocks sheet and the _UnresolvedIndex
report, and writes a populated copy of the I/O List under the output tree. Idempotent and
non-destructive. Exit code: 0 when everything resolved, 1 when entries need manual entry.

Usage:
    python run_populate.py [--params config_project/project_params.yaml] [--out DIR] [--sheets "NET SAFETY"]
"""
from __future__ import annotations
import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from pipeline2.core import config, i18n
from pipeline2 import iolist_diag


def _abs(path: str) -> str:
    return path if os.path.isabs(path) else os.path.normpath(os.path.join(_HERE, path))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Populate a fresh I/O List (script_type/index/diag + DiagnosisBlocks).")
    ap.add_argument("--params", default=None, help="path to params.yaml (default: config_project/project_params.yaml)")
    ap.add_argument("--out", default=None, help="output dir (default: params['output_dir'], else Shared/OutputTree)")
    ap.add_argument("--sheets", default=None, help="override the I/O sheet name(s)/regex (default: io_list.sheet)")
    args = ap.parse_args(argv)

    params = config.load_params(args.params)
    lang = params.get("language") or i18n.DEFAULT_LANG
    out_dir = _abs(args.out) if args.out else config.output_root(params)
    res = iolist_diag.populate(params, sheets_override=args.sheets, lang=lang, out_dir=out_dir)

    if res.audit:
        print(f"\n  audit ({len(res.audit)} pre-filled script_type row(s)):")
        for line in res.audit:
            print("    " + line)
    if res.unresolved:
        print("\n  " + i18n.tr("idiag_halt", lang, n=res.unresolved))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
