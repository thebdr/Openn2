"""Cut a SYCON.net handoff folder (SyconNetProjectInterface) down to the given stations for a smoke build: the
headed csv files are copied with their header and column lines and only those stations' rows (the controller
row always kept), the device-types database as it is.

Usage:  python -I scripts/handoff_cut.py --handoff <folder> --out <folder> --stations <name> [<name> ...]
"""
import argparse
import csv
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sycon5.handoff import DTD_FILE, MODULES_FILE, STATIONS_FILE  # noqa: E402


def cut_file(src, dst, name_column, wanted, keep_row=lambda fields: False):
    with open(src, encoding="utf-8-sig", newline="") as f:
        lines = f.read().splitlines()
    out = []
    for ln in lines:
        if not ln.strip() or ln.lstrip().startswith("#"):
            out.append(ln)
            continue
        fields = next(csv.reader([ln]))
        if len(fields) > name_column and (fields[name_column].lower() in wanted or keep_row(fields)):
            out.append(ln)
    with open(dst, "w", encoding="utf-8", newline="") as f:
        f.write("\r\n".join(out) + "\r\n")
    return sum(1 for ln in out if ln.strip() and not ln.lstrip().startswith("#"))


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--handoff", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--stations", nargs="+", required=True)
    a = p.parse_args(argv)
    wanted = {s.lower() for s in a.stations}
    os.makedirs(a.out, exist_ok=True)
    n = cut_file(os.path.join(a.handoff, STATIONS_FILE), os.path.join(a.out, STATIONS_FILE), 1, wanted,
                 keep_row=lambda fields: fields[0].lower() == "controller")
    m = 0
    if os.path.exists(os.path.join(a.handoff, MODULES_FILE)):
        m = cut_file(os.path.join(a.handoff, MODULES_FILE), os.path.join(a.out, MODULES_FILE), 0, wanted)
    if os.path.exists(os.path.join(a.handoff, DTD_FILE)):
        shutil.copyfile(os.path.join(a.handoff, DTD_FILE), os.path.join(a.out, DTD_FILE))
    print("cut: %d station rows (controller included), %d module rows -> %s" % (n, m, a.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
