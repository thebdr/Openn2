"""Probe - plug the port submodules of an AL1202 from the handoff and prove them by read-back: attached to the
running SYCON.net (the smoke project), `plug_submodules` on the station with the handoff's port rows, then
Save as <out> (inside spike/scratch) and the saved submodules compared with the rows. SYCON.net is left running.

Usage:  ..\\.venv\\Scripts\\python -I scripts\\probe_plug_ports.py [--station n0035-trib-sm006-K1] [--handoff <folder>]
            [--out <spj>]
"""
import argparse
import os
import sys
import time

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP)
from sycon5 import SyconDriver  # noqa: E402
from sycon5.consumer import same_text  # noqa: E402
from sycon5.handoff import load_handoff  # noqa: E402
from sycon5.readback import read_project  # noqa: E402
from sycon5.session import log  # noqa: E402

SMOKE_DIR = os.path.join(APP, "spike", "scratch", "FVT_LowerSorter_smoke")


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--station", default="n0035-trib-sm006-K1")
    p.add_argument("--handoff", default=os.path.join(SMOKE_DIR, "SyconNetProjectInterface"))
    p.add_argument("--out", default=os.path.join(SMOKE_DIR, "Smoke_ports.spj"))
    a = p.parse_args(argv)
    h = load_handoff(a.handoff)
    subs = h.submodule_rows(a.station)
    wanted = sorted((int(m["subslot"]), m["module_text"]) for m in subs if int(m["slot"]) == 1)
    log("wanted on %s slot 1: %r" % (a.station, wanted))
    d = SyconDriver()
    if not d.session.attach_if_running():
        raise SystemExit("SYCON.net is not running")
    t0 = time.time()
    chosen = d.plug_submodules(a.station, 1, wanted)
    log("plugged %d submodules in %.0f s: %r" % (len(chosen), time.time() - t0, chosen))
    xml = d.save_as(a.out)
    project = read_project(xml)
    dev = next(dv for dv in project.devices if dv.device_no.lower() == a.station.lower())
    log("saved submodules of slot 1:", {k: v for k, v in sorted(dev.submodules.items()) if k[0] == 1})
    ok = 0
    for subslot, text in wanted:
        got = dev.submodules.get((1, subslot), "")
        good = same_text(got, text)
        ok += good
        log("%s sub %d: %r (wanted %r)" % ("PASS" if good else "FAIL", subslot, got, text))
    log("%d of %d ports as wanted" % (ok, len(wanted)))
    return 0 if ok == len(wanted) else 1


if __name__ == "__main__":
    raise SystemExit(main())
