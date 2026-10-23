"""Keep only the newest GSDML of every device family in SYCON.net's catalog folder
(C:\\ProgramData\\SYCONnet\\PROFINET\\GSDML): the superseded files are MOVED to a sibling backup folder
(GSDML_superseded_<date>), never deleted. Reload the device catalog in SYCON.net afterwards.

A family = the vendor + family part of the file name (`GSDML-V<schema>-<vendor>-<family>-<yyyymmdd>[suffix].xml`),
normalised (case, spaces, underscores, hyphens). Files with a hand-modification suffix (`_MOD_...`) and the
`#<Vendor>-PreConf_...` per-node exports are their own families (kept, reported) - which of them is "the
newest" is the user's call.

Usage:  python -I scripts/gsdml_dedupe.py [--apply] [--folder <GSDML folder>]
"""
import argparse
import datetime
import os
import re
import shutil
from collections import defaultdict

NAME = re.compile(r"^GSDML-V(?P<schema>\d+(?:\.\d+)*)-(?P<family>.+?)-(?P<date>\d{8})(?P<suffix>.*)\.xml$", re.I)


def norm(text):
    return re.sub(r"[\s_\-]+", "", text).lower()


def classify(files):
    groups, odd = defaultdict(list), []
    for f in files:
        m = NAME.match(f)
        if not m:
            odd.append(f)
            continue
        family, suffix = m.group("family"), m.group("suffix")
        key = norm(family)
        special = family.startswith("#") or "_MOD_" in suffix.upper()
        if special:
            key = norm(family + suffix)                     # its own family: never superseded by a date alone
        groups[key].append({"file": f, "schema": tuple(int(p) for p in m.group("schema").split(".")),
                            "date": m.group("date"), "suffix": suffix, "family": family, "special": special})
    return groups, odd


def plan(folder):
    files = sorted(f for f in os.listdir(folder) if f.lower().endswith(".xml") and os.path.isfile(os.path.join(folder, f)))
    groups, odd = classify(files)
    keep, move, notes = [], [], []
    for key, items in sorted(groups.items()):
        items.sort(key=lambda it: (it["date"], it["schema"]), reverse=True)
        keep.append(items[0]["file"])
        for it in items[1:]:
            move.append((it["file"], items[0]["file"]))
        if items[0]["special"]:
            notes.append(items[0]["file"])
    return keep, move, notes, odd


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--folder", default=r"C:\ProgramData\SYCONnet\PROFINET\GSDML")
    p.add_argument("--apply", action="store_true", help="move the superseded files (default: dry run)")
    a = p.parse_args(argv)
    keep, move, notes, odd = plan(a.folder)
    print("GSDML files: %d | kept %d | superseded %d | special (kept, your call) %d | unparsed %d"
          % (len(keep) + len(move), len(keep), len(move), len(notes), len(odd)))
    for f, by in move:
        print("  superseded  %-70s  by  %s" % (f, by))
    for f in notes:
        print("  special     %s" % f)
    for f in odd:
        print("  unparsed    %s" % f)
    if a.apply and move:
        backup = os.path.join(os.path.dirname(a.folder.rstrip("\\/")),
                              "GSDML_superseded_" + datetime.date.today().strftime("%Y%m%d"))
        os.makedirs(backup, exist_ok=True)
        for f, _by in move:
            shutil.move(os.path.join(a.folder, f), os.path.join(backup, f))
        print("moved %d files to %s" % (len(move), backup))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
