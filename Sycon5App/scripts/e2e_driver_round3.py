"""Round 3 - the driver API end to end (writes the in-memory project and ONE Save as into spike/scratch,
authorized for the rounds of 2026-10-23): new project, controller, ET200SP, controller IP, station name + IP,
one module, two parameters, save as, read back, and the assertions that make the read-back the oracle.

Usage:  C:\\Source\\Repos\\_Openn5\\.venv\\Scripts\\python -I Sycon5App\\scripts\\e2e_driver_round3.py
"""
import os
import sys

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP)
from sycon5 import SyconDriver, DriverError  # noqa: E402
from sycon5.readback import describe  # noqa: E402
from sycon5.session import log  # noqa: E402

SCRATCH = os.path.join(APP, "spike", "scratch")
BASE = os.path.join(SCRATCH, "AutomateSyconProj_BaseProj.spj")
OUT = os.path.join(SCRATCH, "E2E_Round3.spj")
STATION, IP, CTRL_IP = "n0005-ms1-k2501", "192.168.2.5", "192.168.2.1"
MODULE = "DI 8x24VDC HF V2.0  [6ES7 131-6BF00-0CA0]"
PARAMS = {2: "1", 4: "0.4 ms"}           # Channel 0: Wire break diagnostics, Input delay

d = SyconDriver()
if d.session.is_alive() or d.session.attach_if_running():
    log("close the running SYCON.net first:", d.close())
import shutil
for p in (OUT, OUT[:-4]):
    if os.path.isdir(p):
        shutil.rmtree(p)
    elif os.path.exists(p):
        os.remove(p)
d.open(BASE)
try:
    d.new_project()
    ctrl = d.add_controller()
    et = d.add_station("IM 155-6 PN ST V4.2")
    d.set_controller_network(CTRL_IP)
    d.set_station_name_ip(et["station"], STATION, IP)
    d.plug_module(STATION, MODULE)
    d.set_parameters(STATION, 1, PARAMS)
    xml = d.save_as(OUT)
finally:
    log("stations:", d.stations())
p = d.read_back(xml)
print(describe(p))
dev = p.device(STATION)
assert dev.ip == IP and dev.name == STATION, (dev.name, dev.ip)
assert p.controller.network == [(STATION, IP)], p.controller.network
assert dev.slots.get(1) == "DI 8x24VDC HF V2.0", dev.slots
rec = dev.records[(1, 1, 128)]
assert rec[2] == 0x10 and rec[3] == 0x83, rec.hex(" ")
log("ROUND 3 VERIFIED:", STATION, IP, dev.slots[1], rec[:4].hex(" "))
log("close:", d.close())
