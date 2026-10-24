"""Write the canvas (symbolic names, positions) of a SAVED project from its handoff, without SYCON.net - the step
the build does after its last save, for a project built earlier or laid out by hand. The project must be closed.
Usage (from Sycon5App, the repo venv):  python -I scripts\\canvas_apply.py --handoff <folder> --out <project.spj>"""
import argparse
import os
import sys

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP)

from sycon5 import canvas                       # noqa: E402
from sycon5.handoff import load_handoff          # noqa: E402
from sycon5.readback import read_project         # noqa: E402

p = argparse.ArgumentParser(description="lay out the canvas of a saved SYCON.net project from its handoff")
p.add_argument("--handoff", required=True)
p.add_argument("--out", required=True, help="the project .spj (its _S129\\SYCON_net.xml is edited in place)")
a = p.parse_args()
xml = a.out[:-4] + "\\_S129\\SYCON_net.xml"
h = load_handoff(a.handoff)
n_sym, n_rect = canvas.apply_layout(xml, h)
project = read_project(xml)
missing = [s["station_name"] for s in h.stations if s.get("symbolic_name")
           and next((d for d in project.devices if d.device_no.lower() == s["station_name"].lower()), None) is None]
print("canvas: %d symbolic names, %d positions; stations of the table not in the project: %d" % (n_sym, n_rect, len(missing)))
