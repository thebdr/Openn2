"""Re-run the verification of a SAVED project against its handoff, without SYCON.net: the read-back of
`<project>\\_S129\\SYCON_net.xml` compared with the tables, the report rewritten beside the project.
`plugged` is empty (the module texts the driver chose are not known any more - the slots are judged by their
order numbers) and the updating times are the table's (no `timing_set`: a device-limited time shows as a FAIL).
Usage (from Sycon5App, the repo venv):  python -I scripts\\verify_saved.py --handoff <folder> --out <project.spj>"""
import argparse
import os
import sys

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP)

from sycon5 import consumer                      # noqa: E402
from sycon5.readback import describe, read_project   # noqa: E402

p = argparse.ArgumentParser(description="verify a saved SYCON.net project against its handoff")
p.add_argument("--handoff", required=True)
p.add_argument("--out", required=True, help="the project .spj (its _S129\\SYCON_net.xml is read)")
a = p.parse_args()
xml = a.out[:-4] + "\\_S129\\SYCON_net.xml"
h = consumer.load_handoff(a.handoff)
project = read_project(xml)
v = consumer.verify(h, project, {}, None)
report = v.report() + "\n\n" + describe(project)
rpath = a.out[:-4] + ".verification.txt"
with open(rpath, "w", encoding="utf-8") as f:
    f.write(report + "\n")
print(v.report().splitlines()[0])
print("report:", rpath)
sys.exit(0 if v.failed == 0 else 1)
