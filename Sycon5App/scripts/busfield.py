"""`IODriver\\BusField.csv` of a production folder (user 2026-10-24, the FVZ reference
`PRODUCTION\\IODriver\\BusField.csv`): one row per PROFINET node of every cifX card. Board Number = the card,
Physical Node Address = the IP's last octet, Node Type = 0x<VendorID><DeviceID> of the device's GSDML identity as
the saved project records it (`fdt:manufacturerId` / `fdt:deviceTypeId` - the ET200SP's 42 / 787 = 0x002A0313,
the cifX master's 286 / 515 = 0x011E0203), the description `[station] DESCRIPTION (MANUFACTURER) FLD (ip)`.
A row starts with `@` (the node is in the configuration) or `#` (commented out: the master's own station under
the master row - user 2026-10-25: the FVZ reference's `#` switches were switches NOT in that configuration; ours
are configured, so they are `@`). The file opens with the PL5 `#!openn` header (csv form; the IO driver reads `#`
lines as comments). Usage (from Sycon5App, the repo venv):
    python -I scripts\\busfield.py --production <folder>
with `<folder>\\HilscherIOCard<n>\\HilscherPnCard_<n>.spj` and its `SyconNetProjectInterface\\` per card."""
import argparse
import os
import re
import sys
import time

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP)

from sycon5.handoff import load_handoff                 # noqa: E402
from sycon5.readback import read_project                # noqa: E402

HEADER = ("#;Board Number;Physical Node Address;Node Type;1 = Warning on fault;Linked Node Address;Linked Master ID;"
          "Linked Slave ID;Reference Index;DB Class ID;Element;Bit;#;# Description")
CARD_RE = re.compile(r"^HilscherIOCard(\d+)$", re.I)
KIND, SCHEMA = "hw/iodriver-busfield", 1


def header_lines(source) -> list:
    """The PL5 header in csv form (user 2026-10-25: "set the PL5 header here too")."""
    return ["#!openn", "#! kind: %s" % KIND, "#! schema: %d" % SCHEMA,
            "#! producer: Sycon5App busfield.py (the saved SYCON.net projects + their handoffs)",
            "#! generated: %s" % time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "#! target: IODriver", "#! source: %s" % source, "#!end"]


def last_octet(ip) -> str:
    parts = str(ip or "").split(".")
    return parts[-1] if len(parts) == 4 and parts[-1].isdigit() else "0"


def describe(s) -> str:
    """The description column; a `;` inside it would shift the IO driver's columns (C-044 refute round 1)."""
    text = "[%s] %s (%s) %s (%s)" % (s["station_name"], s.get("description", ""), s.get("comment", ""),
                                     s.get("fld", ""), s.get("ip_address", ""))
    return " ".join(text.replace(";", ",").split())


def card_rows(card, handoff, project) -> list:
    """The rows of one card: the master, the master's own station (`#`), every station of the table - `@` when the
    project has it with its GSDML identity, `#` when the project lacks it or records no identity (the IO driver must
    never get a node of type 0x00000000 - C-044 refute round 1)."""
    ctrl = project.controller
    by_name = {d.device_no.lower(): d for d in project.devices}
    rows = ["@;%d;0;%s;0;0;0;0;0;0;0;0;#;Hilscher Master Profinet Card %d" % (card, ctrl.node_type, card),
            "#;%d;%s;%s;0;0;0;0;0;0;0;0;#;%s" % (card, last_octet(handoff.controller["ip_address"]), ctrl.node_type,
                                                   describe(handoff.controller))]
    for s in handoff.stations:
        d = by_name.get(s["station_name"].lower())
        if d is None:
            rows.append("#;%d;%s;0x00000000;0;0;0;0;0;0;0;0;#;%s - NOT IN THE PROJECT" % (card, last_octet(s["ip_address"]), describe(s)))
        elif not (d.manufacturer_id and d.device_type_id):
            rows.append("#;%d;%s;%s;0;0;0;0;0;0;0;0;#;%s - NO DEVICE IDENTITY IN THE PROJECT" % (card, last_octet(s["ip_address"]), d.node_type, describe(s)))
        else:
            rows.append("@;%d;%s;%s;0;0;0;0;0;0;0;0;#;%s" % (card, last_octet(s["ip_address"]), d.node_type, describe(s)))
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
    body, sources = [], []
    for n, handoff_dir, spj in cards_of(production):
        if not os.path.exists(spj):
            print("card %d: no project %s - skipped" % (n, spj))
            continue
        h = load_handoff(handoff_dir)
        p = read_project(spj)
        if p.controller is None:
            print("card %d: no controller in %s - skipped" % (n, spj))
            continue
        body += card_rows(n, h, p)
        sources.append("HilscherIOCard%d/HilscherPnCard_%d" % (n, n))
        print("card %d: %d nodes" % (n, len(h.stations)))
    rows = header_lines(", ".join(sources)) + [HEADER] + body        # the header names the cards written, no other
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
