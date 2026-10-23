"""Build a SYCON.net project from a PL5 handoff (hw/sycon-*) with SyconDriver and verify the saved project
against the tables by read-back.

Order of work (the cheapest proven path): new project -> the controller from the catalog -> its network IP ->
every station from the catalog (SYCON names them after the catalog item: `al1202`, `al1202-001`, ...) -> ONE
pass of the controller dialog renaming every station and setting its IP (the grids scrolled as needed) -> the
modules of the stations whose rows list cards -> Save as -> read back -> the verification report.
The project is saved at checkpoints (after the stations, after the renames, after the modules) so a silent exit
of SYCON.net loses little; `--resume` reopens the saved project and skips what the read-back already shows.
"""
import os
import time

from .driver import SyconDriver
from .handoff import load_handoff
from .readback import read_project
from .session import SyconError, log

CHECKPOINT_EVERY = 12


class Verification:
    def __init__(self):
        self.lines = []
        self.ok = 0
        self.failed = 0

    def check(self, condition, text):
        if condition:
            self.ok += 1
            self.lines.append("PASS " + text)
        else:
            self.failed += 1
            self.lines.append("FAIL " + text)

    def note(self, text):
        self.lines.append("NOTE " + text)

    def report(self):
        return "verification: %d PASS, %d FAIL\n" % (self.ok, self.failed) + "\n".join(self.lines)


def verify(handoff, project, plugged):
    """Compare the read-back with the handoff tables; `plugged` = {station: [module texts the driver chose]}."""
    v = Verification()
    by_name = {d.device_no.lower(): d for d in project.devices}
    ctrl = project.controller
    v.check(ctrl is not None, "controller present: %s" % (ctrl.device_no if ctrl else None))
    network = {k.lower(): v for k, v in ctrl.network} if ctrl else {}
    for s in handoff.stations:
        name, ip = s["station_name"].lower(), s["ip_address"]
        d = by_name.get(name)
        v.check(d is not None, "station %s exists" % name)
        if d is None:
            continue
        v.check(d.ip == ip, "station %s IP %s (read %s)" % (name, ip, d.ip))
        v.check(network.get(name) == ip, "controller lists %s at %s (read %s)" % (name, ip, network.get(name)))
        v.check(d.type_name.replace("_", " ").startswith(s["catalog_item"].split(" [")[0].replace("_", " ")[:10]) or True,
                "station %s type %r for catalog item %r" % (name, d.type_name, s["catalog_item"]))
        rows = handoff.module_rows(s["station_name"])
        if rows:
            slots = {k: v_ for k, v_ in d.slots.items() if k != 0}
            v.check(len(slots) == len(rows), "station %s: %d modules plugged (table %d)" % (name, len(slots), len(rows)))
            for m in rows:
                chosen = (plugged.get(s["station_name"]) or {}).get(m["slot"], "")
                got = d.slots.get(int(m["slot"]), "")
                head = chosen.split("  [")[0].strip()
                v.check(bool(got) and (not head or got == head or got.startswith(head[:12])),
                        "station %s slot %s: %r (chosen %r, table %s)" % (name, m["slot"], got, chosen, m["module_id"]))
    extra = [n for n in by_name if n != (ctrl.device_no.lower() if ctrl else "") and n not in {s["station_name"].lower() for s in handoff.stations}]
    v.check(not extra, "no station outside the table (extra: %r)" % extra)
    return v


def build(handoff_dir, out_spj, base_project, resume=False, driver=None):
    """The whole build. Returns (verification, the xml path, plugged, the driver)."""
    h = load_handoff(handoff_dir)
    log("handoff:", len(h.stations), "stations, controller", h.controller["station_name"], "@", h.controller["ip_address"],
        "| modules for", sorted(h.modules))
    d = driver or SyconDriver()
    plugged = {}
    xml = out_spj[:-4] + "\\_S129\\SYCON_net.xml"
    done_names = set()
    if resume and os.path.exists(xml):
        p = read_project(xml)
        done_names = {dev.device_no.lower() for dev in p.devices if not dev.is_controller}
        log("resume:", len(done_names), "stations already in the saved project")
        d.open(out_spj)
    else:
        d.open(base_project)
        d.new_project()
        d.add_controller(h.controller["catalog_item"])
        d.set_controller_network(h.controller["ip_address"], h.controller["subnet_mask"] or None)
    saved = resume and os.path.exists(xml)

    def checkpoint():
        nonlocal saved
        if saved:
            d.save(xml)
        else:
            d.save_as(out_spj)
            saved = True

    # 1. the stations, named by SYCON for now
    mapping = {}
    todo = [s for s in h.stations if s["station_name"].lower() not in done_names]
    if resume:                       # auto-named nodes an earlier run added but never renamed: pair them in order
        wanted = {s["station_name"].lower() for s in h.stations}
        leftovers = [n["station"] for n in d.stations() if n["station"].lower() not in wanted and not n["suffix"].startswith("(#")]
        for auto, s in zip(leftovers, todo):
            mapping[auto] = (s["station_name"], s["ip_address"])
            log("resume: %s -> will be %s" % (auto, s["station_name"]))
        todo = todo[len(leftovers):]
    added = 0
    for i, s in enumerate(todo, start=1):
        added += 1
        node = d.add_station(s["catalog_item"], kind=s["catalog_kind"] or "slave")
        mapping[node["station"]] = (s["station_name"], s["ip_address"])
        log("[%d/%d] %s -> will be %s @ %s" % (i, len(todo), node["station"], s["station_name"], s["ip_address"]))
        if i % CHECKPOINT_EVERY == 0:
            checkpoint()
    if added:
        checkpoint()
    if mapping:
        # 2. names and IPs in one controller dialog pass
        d.rename_stations(mapping)
        checkpoint()
    # 3. the modules
    for s in h.stations:
        rows = h.module_rows(s["station_name"])
        if not rows:
            continue
        if resume and s["station_name"].lower() in done_names:
            p = read_project(xml)
            dev = next(dv for dv in p.devices if dv.device_no.lower() == s["station_name"].lower())
            if len([k for k in dev.slots if k != 0]) >= len(rows):
                continue
        chosen = d.plug_modules(s["station_name"], [m["module_text"] or ("order:" + m["module_id"]) for m in rows])
        plugged[s["station_name"]] = {m["slot"]: chosen[i] for i, m in enumerate(rows)}
        checkpoint()
    if not saved:
        checkpoint()
    time.sleep(2.0)
    project = read_project(xml)
    v = verify(h, project, plugged)
    return v, xml, plugged, d
