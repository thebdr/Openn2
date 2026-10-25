"""Apply the handoff's DAP rows (slot 0: a device's own submodule parameters and port submodules) to a SAVED project
without a full build: open, one device dialog per station that has them, save, close, read back. For a change of
the device-types database's `DAP Parameters` column on a built project (user 2026-10-25: the PN/PN couplers'
Diagnostics data validity = 0).
Usage (from Sycon5App, the repo venv):  python -I scripts\\apply_dap_params.py --handoff <folder> --out <project.spj>"""
import argparse
import os
import sys
import time

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP)

from sycon5 import SyconDriver                       # noqa: E402
from sycon5.handoff import load_handoff, parse_parameters   # noqa: E402
from sycon5.readback import read_project             # noqa: E402
from sycon5.session import log                       # noqa: E402

p = argparse.ArgumentParser()
p.add_argument("--handoff", required=True)
p.add_argument("--out", required=True, help="the project .spj")
p.add_argument("--station", default="", help="one station only (default: every station with DAP rows)")
a = p.parse_args()
h = load_handoff(a.handoff)
xml = a.out[:-4] + "\\_S129\\SYCON_net.xml"
d = SyconDriver()
code = 1
try:
    d.open(a.out)
    done = []
    for s in h.stations:
        station = s["station_name"]
        if a.station and station.lower() != a.station.lower():
            continue
        daps = h.dap_rows(station)
        if not daps:
            continue
        ports = [(int(m["subslot"]), m["module_text"]) for m in daps if m["module_text"] and int(m["subslot"]) > 0x8000]
        if ports:
            d.set_dap_submodules(station, sorted(ports))
        for m in daps:
            params = [(n, v) for n, v in parse_parameters(m["parameters"]) if not str(n).startswith("record:")]
            if params:
                d.set_module_parameters(station, 0, params, subslot=int(m["subslot"]))
        done.append(station)
    d.save(xml)
    time.sleep(2.0)
    log("close:", d.close())
    project = read_project(xml)
    bad = []
    for s in h.stations:
        if s["station_name"] not in done:
            continue
        dev = next((dv for dv in project.devices if dv.device_no.lower() == s["station_name"].lower()), None)
        for m in h.dap_rows(s["station_name"]):
            for n, v in parse_parameters(m["parameters"]):
                if str(n).startswith("record:"):
                    idx = int(str(n)[7:])
                    want = bytes.fromhex(v.replace(" ", ""))
                    got = dev.records.get((0, int(m["subslot"]), idx), b"") if dev else b""
                    ok = got[:len(want)] == want
                    log("  %s record %d: %s (want %s) %s" % (s["station_name"], idx, got.hex(" ") or "nothing", want.hex(" "), "OK" if ok else "FAIL"))
                    if not ok:
                        bad.append(s["station_name"])
    log("DAP rows applied on %d stations; %d record mismatches" % (len(done), len(bad)))
    code = 0 if not bad else 1
finally:
    log("close:", d.close())
sys.exit(code)
