"""`IODriver\\BusField.csv` of a production folder (user 2026-10-24, the FVZ reference
`PRODUCTION\\IODriver\\BusField.csv`): one row per PROFINET node of every cifX card. Board Number = the card,
Physical Node Address = the IP's last octet, Node Type = 0x<VendorID><DeviceID> of the device's GSDML identity as
the saved project records it (`fdt:manufacturerId` / `fdt:deviceTypeId` - the ET200SP's 42 / 787 = 0x002A0313,
the cifX master's 286 / 515 = 0x011E0203), the description `[station] DESCRIPTION (MANUFACTURER) FLD (ip)`.
A row starts with `@` (the IO driver polls the node) or `#` (listed, not polled: the master's own station and
the switches). Usage (from Sycon5App, the repo venv):
    python -I scripts\\busfield.py --production <folder>
with `<folder>\\HilscherIOCard<n>\\HilscherPnCard_<n>.spj` and its `SyconNetProjectInterface\\` per card."""
import argparse
import csv
import os
import re
import sys

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP)

from sycon5.handoff import load_handoff                 # noqa: E402
from sycon5.readback import read_project                # noqa: E402

HEADER = ("#;Board Number;Physical Node Address;Node Type;1 = Warning on fault;Linked Node Address;Linked Master ID;"
          "Linked Slave ID;Reference Index;DB Class ID;Element;Bit;#;# Description")
CARD_RE = re.compile(r"^HilscherIOCard(\d+)$", re.I)
NOT_POLLED = ("scalance-pnio",)                          # the policies of the nodes the IO driver does not poll


def policies(handoff_folder) -> dict:
    """{MODEL ID upper: modules policy} from the shipped device-types database (column 4)."""
    path = os.path.join(handoff_folder, "SyconDeviceTypesDatabase.csv")
    out = {}
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8-sig") as f:
        lines = [ln for ln in f.read().splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    for row in csv.reader(lines):
        if row and row[0].strip():
            out[row[0].replace(" ", "").strip().upper()] = (row[3].strip().lower() if len(row) > 3 else "") or "default"
    return out


def last_octet(ip) -> str:
    parts = str(ip or "").split(".")
    return parts[-1] if len(parts) == 4 and parts[-1].isdigit() else "0"


def describe(s) -> str:
    return "[%s] %s (%s) %s (%s)" % (s["station_name"], s.get("description", ""), s.get("comment", ""),
                                     s.get("fld", ""), s.get("ip_address", ""))


def card_rows(card, handoff, project) -> list:
    ctrl = project.controller
    by_name = {d.device_no.lower(): d for d in project.devices}
    pol = policies(handoff.folder)
    rows = ["@;%d;0;%s;0;0;0;0;0;0;0;0;#;Hilscher Master Profinet Card %d" % (card, ctrl.node_type, card),
            "#;%d;%s;%s;0;0;0;0;0;0;0;0;#;%s" % (card, last_octet(handoff.controller["ip_address"]), ctrl.node_type,
                                                   describe(handoff.controller))]
    for s in handoff.stations:
        d = by_name.get(s["station_name"].lower())
        if d is None:
            rows.append("#;%d;%s;0x00000000;0;0;0;0;0;0;0;0;#;%s - NOT IN THE PROJECT" % (card, last_octet(s["ip_address"]), describe(s)))
            continue
        flag = "#" if pol.get(str(s.get("model_id", "")).upper()) in NOT_POLLED else "@"
        rows.append("%s;%d;%s;%s;0;0;0;0;0;0;0;0;#;%s" % (flag, card, last_octet(s["ip_address"]), d.node_type, describe(s)))
    return rows


def cards_of(production) -> list:
    """[(card number, handoff folder, project .spj)] of the production folder, by card number."""
    out = []
    for entry in os.listdir(production):
        m = CARD_RE.match(entry)
        if not m:
            continue
        n = int(m.group(1))
        folder = os.path.join(production, entry)
        spj = os.path.join(folder, "HilscherPnCard_%d.spj" % n)
        out.append((n, os.path.join(folder, "SyconNetProjectInterface"), spj))
    return sorted(out)


def write_busfield(production) -> str:
    rows = [HEADER]
    for n, handoff_dir, spj in cards_of(production):
        if not os.path.exists(spj):
            print("card %d: no project %s - skipped" % (n, spj))
            continue
        h = load_handoff(handoff_dir)
        p = read_project(spj)
        rows += card_rows(n, h, p)
        print("card %d: %d nodes" % (n, len(h.stations)))
    out_dir = os.path.join(production, "IODriver")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "BusField.csv")
    with open(path, "w", encoding="ascii", errors="replace", newline="") as f:
        f.write("\r\n".join(rows) + "\r\n")
    return path


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="write IODriver/BusField.csv of a production folder")
    ap.add_argument("--production", required=True)
    a = ap.parse_args()
    print("BusField:", write_busfield(a.production))
