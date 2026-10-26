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
import shutil
import time

from . import canvas, exports
from .catalog import split_item
from .driver import SyconDriver
from .handoff import load_handoff, natural_key, parse_parameters
from .readback import read_project
from .session import Session, SyconError, log

CHECKPOINT_EVERY = 12
# the files shipped into the project's nWid\ folder beside config.nxd (user 2026-10-24: the FVZ reference's
# UpdateCardV4.bat as UpdateCardV5.bat, with the chosen card remembered in card.txt) - hand-maintained in Shared
NWID_ASSETS = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "Shared",
                                            "HardwareConfigBuilderData", "nWid"))
POTENTIAL_GROUP_RECORD = 243          # an ET200SP module's `Potential group` record (its first byte 01 = a new group)


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


same_text = Session.same_text


def order_is_pattern(order):
    """A GSDML DAP whose OrderNumber is not a literal: a wildcard pattern (`13xx.xx7x.xxxx.x`, the LTi ServoOne
    Junior) or a placeholder token (`T_ID_DAP_DESCRIPTION`, the Anybus Communicator) - 2026-10-24, the sorter's
    27 false FAILs; the type and the DAP are still compared, the order number noted."""
    o = str(order or "").strip()
    return o.startswith("T_ID_") or "x" in o


def verify(handoff, project, plugged, timing_set=None, skipped=None, keep_extras=False):
    """Compare the read-back with the handoff tables; `plugged` = {station: [module texts the driver chose]},
    `timing_set` = {station: the updating time (ms) the driver could set when the table's was not offered}. An
    update (`skipped` = the lower-case names the project already had, `keep_extras`): a skipped station is a NOTE,
    not compared; a node the table does not name is a NOTE, not a FAIL; a controller that keeps its own name or
    address is a NOTE."""
    v = Verification()
    timing_set = {k.lower(): v_ for k, v_ in (timing_set or {}).items()}
    by_name = {d.device_no.lower(): d for d in project.devices}
    ctrl = project.controller
    v.check(ctrl is not None, "controller present: %s" % (ctrl.device_no if ctrl else None))
    twice = sorted({d.device_no.lower() for d in project.devices if [x.device_no.lower() for x in project.devices].count(d.device_no.lower()) > 1})
    v.check(not twice, "no station name twice in the project (twice: %r)" % twice)   # C-047 refute round 1
    if ctrl is not None:              # the controller's own name of station and address (user 2026-10-26)
        want_name, want_ip = handoff.controller["station_name"], handoff.controller.get("ip_address", "")
        if skipped is not None and not controller_is_unnamed(ctrl.name) and ctrl.name.lower() != want_name.lower():
            v.note("controller name of station %r kept (table %s) - an update leaves a named controller as it is" % (ctrl.name, want_name))
        else:
            v.check(ctrl.name.lower() == want_name.lower(), "controller name of station %s (read %r)" % (want_name, ctrl.name))
        if skipped is not None and ctrl.ip != want_ip:
            v.note("controller IP %s kept (table %s) - an update leaves the controller's address" % (ctrl.ip, want_ip))
        else:
            v.check(ctrl.ip == want_ip, "controller IP %s (read %s)" % (want_ip, ctrl.ip))
    network = {k.lower(): v for k, v in ctrl.network} if ctrl else {}
    timing = {k.lower(): v for k, v in ctrl.timing.items()} if ctrl else {}
    for s in handoff.stations:
        name, ip = s["station_name"].lower(), s["ip_address"]
        if skipped and name in skipped:
            v.note("station %s exists in the project - skipped, not compared (update)" % name)
            continue
        d = by_name.get(name)
        v.check(d is not None, "station %s exists" % name)
        if d is None:
            continue
        v.check(d.ip == ip, "station %s IP %s (read %s)" % (name, ip, d.ip))
        v.check(network.get(name) == ip, "controller lists %s at %s (read %s)" % (name, ip, network.get(name)))
        if s.get("update_time_ms"):
            t = timing.get(name)
            want = float(timing_set.get(name, s["update_time_ms"]))
            if abs(want - float(s["update_time_ms"])) > 1e-6:
                v.note("station %s: the table's %s ms is not offered by the device, %g ms set" % (name, s["update_time_ms"], want))
            v.check(t is not None and abs(t[0] - want) < 1e-6,
                    "station %s update time %g ms (read %s)" % (name, want, "%g ms, watchdog %g ms" % t if t else None))
        if s.get("gsdml"):
            v.check(d.gsdml.lower() == s["gsdml"].lower(),
                    "station %s GSDML %s (read %s)" % (name, s["gsdml"], d.gsdml))
        else:
            v.note("station %s type %r from %s (no GSDML in the table)" % (name, d.type_name, d.gsdml))
        type_name, variant = split_item(s["catalog_item"])
        v.check(same_text(d.type_name, type_name), "station %s type %r (read %r)" % (name, type_name, d.type_name))
        if s.get("symbolic_name"):                    # the netDevice label (canvas.apply_layout wrote it)
            v.check(d.symbolic == s["symbolic_name"], "station %s symbolic name %r (read %r)" % (name, s["symbolic_name"], d.symbolic))
        v.check(bool(d.manufacturer_id and d.device_type_id), "station %s node type %s" % (name, d.node_type))
        if variant:
            v.check(same_text(d.dap, variant), "station %s DAP %s (read %r)" % (name, variant, d.dap))
        if d.order_no and s.get("model_id"):          # the DAP's order number = the I/O List's Part No.
            if order_is_pattern(d.order_no):
                v.note("station %s model %s: the GSDML's order number is the pattern %r - not compared" % (name, s["model_id"], d.order_no))
            else:
                v.check(d.order_no.replace(" ", "").upper() == s["model_id"].replace(" ", "").upper(),
                        "station %s model %s (the saved DAP %r is order %s)" % (name, s["model_id"], d.dap, d.order_no))
        rows = handoff.plug_rows(s["station_name"])
        if rows:
            slots = {k: v_ for k, v_ in d.slots.items() if k != 0}
            v.check(len(slots) == len(rows), "station %s: %d modules plugged (table %d)" % (name, len(slots), len(rows)))
            for m in rows:
                chosen = (plugged.get(s["station_name"]) or {}).get(m["slot"], "")
                got = d.slots.get(int(m["slot"]), "")
                head = chosen.split("  [")[0].strip()
                v.check(bool(got) and (not head or got == head or got.startswith(head[:12])),
                        "station %s slot %s: %r (chosen %r, table %s)" % (name, m["slot"], got, chosen, m["module_id"]))
                for pname, pvalue in parse_parameters(m["parameters"]):
                    if pname == "potential_group":
                        rec = d.records.get((int(m["slot"]), 1, POTENTIAL_GROUP_RECORD), b"")
                        want = b"\x01" if pvalue.lower().startswith("enable new") else b"\x00"
                        v.check(rec[:1] == want, "station %s slot %s potential group %r (record %d reads %s)" % (
                            name, m["slot"], pvalue, POTENTIAL_GROUP_RECORD, rec.hex(" ") or "nothing"))
                    else:
                        v.note("station %s slot %s parameter %s=%s set through the GUI (read back there)" % (
                            name, m["slot"], pname, pvalue))
        for m in handoff.submodule_rows(s["station_name"]):
            got = d.submodules.get((int(m["slot"]), int(m["subslot"])), "")
            v.check(same_text(got, m["module_text"]),
                    "station %s slot %s sub %s: %r (table %r)" % (name, m["slot"], m["subslot"], got, m["module_text"]))
        for m in handoff.dap_rows(s["station_name"]):
            if m["module_text"] and int(m["subslot"]) > 0x8000:          # a pluggable port of the device itself
                got = d.submodules.get((0, int(m["subslot"])), "")
                v.check(same_text(got, m["module_text"]) or same_text(got.split(" - ")[-1], m["module_text"]),
                        "station %s slot 0 sub %s: %r (table %r)" % (name, m["subslot"], got, m["module_text"]))
        for m in handoff.dap_rows(s["station_name"]) + handoff.submodule_rows(s["station_name"]):
            for pname, pvalue in parse_parameters(m["parameters"]):
                if pname.startswith("record:"):
                    idx = int(pname[7:])
                    want = bytes.fromhex(pvalue.replace(" ", ""))
                    rec = d.records.get((int(m["slot"]), int(m["subslot"]), idx), b"")
                    v.check(rec[:len(want)] == want, "station %s slot %s sub %s record %d: %s (table %s)" % (
                        name, m["slot"], m["subslot"], idx, rec[:len(want)].hex(" ") or "nothing", want.hex(" ")))
    extra = [n for n in by_name if n != (ctrl.device_no.lower() if ctrl else "") and n not in {s["station_name"].lower() for s in handoff.stations}]
    if keep_extras:
        for n in extra:
            v.note("node %s in the project is not in the table - kept (update)" % n)
    else:
        v.check(not extra, "no station outside the table (extra: %r)" % extra)
    return v


def type_key(s):
    return (s["catalog_kind"] or "slave", s["catalog_item"], (s.get("gsdml") or "").lower())


def structure(h, station):
    """What a clone carries from its source: the modules (slot, text or order number, parameters), the submodule
    subslots per slot (their types may differ - they are re-typed in place) and the device's own rows."""
    rows, subs, daps = h.plug_rows(station), h.submodule_rows(station), h.dap_rows(station)
    return (tuple((m["slot"], m["module_text"] or ("order:" + m["module_id"]), m["parameters"]) for m in rows),
            tuple(sorted((m["slot"], m["subslot"]) for m in subs)),
            tuple((m["subslot"], m["module_text"], m["parameters"]) for m in daps))


def clone_safe(h, stations):
    """Every station of the model shares the structure: the first configured, then cloned, serves them all."""
    return len({structure(h, st["station_name"]) for st in stations}) == 1


def params_satisfied(dev, slot, subslot, parameters):
    """True when the read-back already shows every oracle of a parameter row (the potential group's record, the
    record:<idx> entries); a row with plain index=value entries and no oracle is never known satisfied."""
    params = parse_parameters(parameters)
    if not params:
        return True
    oracles = 0
    for name, value in params:
        if name == "potential_group":
            rec = dev.records.get((slot, subslot, POTENTIAL_GROUP_RECORD), b"")
            if rec[:1] != (b"\x01" if value.lower().startswith("enable new") else b"\x00"):
                return False
            oracles += 1
        elif str(name).startswith("record:"):
            rec = dev.records.get((slot, subslot, int(str(name)[7:])), b"")
            want = bytes.fromhex(value.replace(" ", ""))
            if rec[:len(want)] != want:
                return False
            oracles += 1
    return oracles > 0


def apply_station(d, h, station, dev, plugged, node=None):
    """The table's rows of `station` applied to the node `node` (its auto name before the rename; the station's
    own name afterwards), given the read-back `dev` of that node (None = nothing known: everything is done).
    Returns True when a dialog changed something."""
    node = node or station
    rows, subs, daps = h.plug_rows(station), h.submodule_rows(station), h.dap_rows(station)
    if not rows and not subs and not daps:
        return False
    changed = False
    ports = sorted((int(m["subslot"]), m["module_text"]) for m in daps if m["module_text"] and int(m["subslot"]) > 0x8000)
    if ports and (dev is None or any(not same_text(dev.submodules.get((0, sub), ""), text) for sub, text in ports)):
        d.set_dap_submodules(node, ports)
        changed = True
    for m in daps:
        if m["parameters"] and (dev is None or not params_satisfied(dev, 0, int(m["subslot"]), m["parameters"])):
            d.set_module_parameters(node, 0, parse_parameters(m["parameters"]), subslot=int(m["subslot"]))
            changed = True
    have = {k for k in (dev.slots if dev is not None else {}) if k != 0}
    if rows and not all(int(m["slot"]) in have for m in rows):
        chosen = d.plug_modules(node, [m["module_text"] or ("order:" + m["module_id"]) for m in rows])
        plugged[station] = {m["slot"]: chosen[i] for i, m in enumerate(rows)}
        changed, dev = True, None                                 # the read-back is stale from here
    for m in rows:
        if m["parameters"] and (dev is None or not params_satisfied(dev, int(m["slot"]), 1, m["parameters"])):
            d.set_module_parameters(node, int(m["slot"]), parse_parameters(m["parameters"]))
            changed = True
    by_slot = {}
    for m in subs:
        by_slot.setdefault(int(m["slot"]), []).append((int(m["subslot"]), m["module_text"]))
    for slot, wanted in sorted(by_slot.items()):
        wanted = sorted(wanted)
        if dev is None or not all(dev.submodules.get((slot, sub)) for sub, _t in wanted):
            d.plug_submodules(node, slot, wanted)
            changed = True
        else:
            differing = [(sub, text) for sub, text in wanted if not same_text(dev.submodules.get((slot, sub), ""), text)]
            if differing:
                d.set_submodules(node, slot, differing)
                changed = True
    return changed


def controller_is_unnamed(name):
    """A controller still called by SYCON.net's default (`controller`) or nothing - its name of station never set."""
    return str(name or "").strip().lower() in ("", "controller")


def build(handoff_dir, out_spj, base_project, resume=False, driver=None, update=False):
    """The whole build. `resume`: an interrupted build of this handoff goes on in its saved project. `update` (user
    2026-10-26: "update an already existing sycon project, like OP5 did by skipping existing nodes with matching pn
    name"): the saved project is brought up to the table - a station whose PROFINET name the project already has is
    skipped whole, never completed or compared (OP5's rule), the project's other nodes are kept and noted, the new
    stations are added, named, addressed, configured and laid out around what is there; the controller's own name
    of station is set when it is still the default, else kept and noted. Returns (verification, the xml path,
    plugged, the driver)."""
    h = load_handoff(handoff_dir)
    log("handoff:", len(h.stations), "stations, controller", h.controller["station_name"], "@", h.controller["ip_address"],
        "| modules for", sorted(h.modules))
    d = driver or SyconDriver()
    plugged = {}
    xml = out_spj[:-4] + "\\_S129\\SYCON_net.xml"
    done_names, saved_devices, extras, saved_controller = set(), {}, [], None
    if update and not os.path.exists(xml):
        raise SyconError("nothing to update: no saved project at %s" % xml)
    if (resume or update) and os.path.exists(xml):
        p = read_project(xml)
        saved_devices = {dev.device_no.lower(): dev for dev in p.devices if not dev.is_controller}
        saved_controller = p.controller
        done_names = set(saved_devices)
        log("update:" if update else "resume:", len(done_names), "stations already in the saved project")
        d.open(out_spj)
    else:
        d.open(base_project)
        d.new_project()
        d.add_controller(h.controller["catalog_item"], h.controller.get("gsdml"))
        d.set_controller_network(h.controller["ip_address"], h.controller["subnet_mask"] or None,
                                 name=h.controller["station_name"])
    saved = (resume or update) and os.path.exists(xml)

    def checkpoint():
        nonlocal saved
        if saved:
            d.save(xml)
        else:
            d.save_as(out_spj)
            saved = True

    controller_kept = False
    if update and saved_controller is not None:
        if controller_is_unnamed(saved_controller.name):
            d.set_controller_network(None, None, None, name=h.controller["station_name"])
            log("update: the controller named %s (it was %r)" % (h.controller["station_name"], saved_controller.name))
            checkpoint()
        elif saved_controller.name.lower() != h.controller["station_name"].lower():
            controller_kept = True
            log("update: the controller keeps its name %r (the table says %s)" % (saved_controller.name, h.controller["station_name"]))

    # 1. the stations, named by SYCON for now. The table's stations are added by TYPE (kind, catalog item, GSDML) and,
    # within a type, by MODEL (the types in the order of their first name, the models likewise, the names in natural
    # order within a model - user 2026-10-24: "since devices of the same type are cloned, i would expect them to be
    # consecutive in the sycon project", "sorted naturally by profinet name"). The first station of each model is
    # configured with what all its stations share BEFORE it is cloned - its modules, its own submodules' ports and
    # parameters, an AL1202's eight ports with that station's types - so the clones carry it and step 3 only changes
    # what differs (user 2026-10-25). A model whose stations differ in structure (an ET200SP with other cards) is
    # cloned unconfigured and configured station by station.
    mapping = {}
    first_of = {}                    # (type key, model) -> the auto name of a node of that model (the clone source)
    todo = [s for s in h.stations if s["station_name"].lower() not in done_names]
    todo.sort(key=lambda s: natural_key(s["station_name"]))
    groups = {}
    for s in todo:
        groups.setdefault(type_key(s), {}).setdefault(s["model_id"].upper(), []).append(s)
    ordered = [s for by_model in groups.values() for members in by_model.values() for s in members]
    if update:                       # the project's nodes the table does not name are kept, never paired or renamed
        wanted = {s["station_name"].lower() for s in h.stations}
        extras = [n["station"] for n in d.stations() if n["station"].lower() not in wanted and not n["suffix"].startswith("(#")]
        for extra in extras:
            log("update: node %s is not in the table - kept" % extra)
    if resume and not update:        # auto-named nodes an earlier run added but never renamed: pair them with the
        wanted = {s["station_name"].lower() for s in h.stations}      # table's stations of the SAME type, in order
        leftovers = [n for n in d.stations() if n["station"].lower() not in wanted and not n["suffix"].startswith("(#")]
        remaining = []
        for s in ordered:
            type_name = split_item(s["catalog_item"])[0]
            match = next((n for n in leftovers if same_text(n["type"], type_name)), None)
            if match is None:
                remaining.append(s)
                continue
            leftovers.remove(match)
            mapping[match["station"]] = (s["station_name"], s["ip_address"])
            first_of.setdefault((type_key(s), s["model_id"].upper()), match["station"])
            log("resume: %s -> will be %s" % (match["station"], s["station_name"]))
        if leftovers:
            raise SyconError("saved nodes no table station of their type is left for: %r" % [n["station"] for n in leftovers])
        keep = {s["station_name"] for s in remaining}
        groups = {}
        for s in [s for s in ordered if s["station_name"] in keep]:
            groups.setdefault(type_key(s), {}).setdefault(s["model_id"].upper(), []).append(s)
    added, i, total = 0, 0, sum(len(m) for by_model in groups.values() for m in by_model.values())

    def assign(node, s):
        nonlocal added, i
        mapping[node["station"]] = (s["station_name"], s["ip_address"])
        added, i = added + 1, i + 1
        log("[%d/%d] %s -> will be %s @ %s" % (i, total, node["station"], s["station_name"], s["ip_address"]))

    for key, by_model in groups.items():
        # (a) a node per model: the first from the catalog (or the type's leftover of the resume), the other models'
        # heads cloned from it while it is still unconfigured - else from the catalog
        heads, fresh_head = {}, None
        for model, members in by_model.items():
            if (key, model) in first_of:
                continue                                        # a resume: a node of the model exists
            s0 = members[0]
            if fresh_head is None:
                node = d.add_station(s0["catalog_item"], kind=s0["catalog_kind"] or "slave", gsdml=s0.get("gsdml"))
                fresh_head = node["station"]
            else:
                node = d.clone_station(fresh_head, 1)[0]
            first_of[(key, model)] = node["station"]
            heads[model] = (node["station"], s0)
            assign(node, s0)
            by_model[model] = members[1:]
        # (b) the heads configured with their model's common configuration, when every station of the model
        # shares the head's structure
        for model, (node_name, s0) in heads.items():
            all_of_model = [st for st in h.stations if st["model_id"].upper() == model and type_key(st) == key]
            if clone_safe(h, all_of_model):
                if apply_station(d, h, s0["station_name"], None, plugged, node=node_name):
                    log("  %s configured before cloning (%s)" % (node_name, s0["station_name"]))
            else:
                log("  %s not configured before cloning: the %s stations differ in structure" % (node_name, model))
        if heads:
            checkpoint()
        # (c) the clones of each model, from its head - by doubling, a checkpoint every 8 or so
        for model, members in by_model.items():
            if not members:
                continue
            for node, s in zip(d.clone_station(first_of[(key, model)], len(members), after_batch=checkpoint), members):
                assign(node, s)
            checkpoint()
    if added:
        checkpoint()
    # a resume: the named stations whose saved IP is not the table's (an IP pass that failed midway kept its names
    # and the IPs written so far) are re-addressed, their names unchanged (an update never touches a matched station)
    for s in ([] if update else h.stations):
        dev = saved_devices.get(s["station_name"].lower())
        if dev is not None and s["ip_address"] and dev.ip != s["ip_address"]:
            mapping[dev.device_no] = (s["station_name"], s["ip_address"])
            log("resume: %s keeps its name, IP %s -> %s" % (dev.device_no, dev.ip, s["ip_address"]))
    if mapping:
        # 2. names and IPs in one controller dialog pass - saved even when the pass fails (the names and IPs it did
        # write stay; a resume pairs and re-addresses the rest), so a failure costs the pass, not the project state
        current = {dev.device_no: dev.ip for dev in saved_devices.values() if dev.ip}   # a resume knows them
        try:
            d.rename_stations(mapping, current_ips=current)
        except SyconError:
            checkpoint()
            raise
        checkpoint()
    # 2b. the stations' updating times (one Stations Timing pass; on a resume only the ones the saved project shows wrong)
    wanted = {s["station_name"]: float(s["update_time_ms"]) for s in h.stations if s.get("update_time_ms")}
    if update:
        wanted = {st: ms for st, ms in wanted.items() if st.lower() not in done_names}      # the new stations alone
    if wanted and resume and not update and os.path.exists(xml):
        have = {k.lower(): v for k, v in read_project(xml).controller.timing.items()}
        wanted = {st: ms for st, ms in wanted.items() if not have.get(st.lower()) or abs(have[st.lower()][0] - ms) > 1e-6}
    timing_set = {}
    if wanted:
        shown = d.set_stations_timing(wanted)
        timing_set = {st: float(upd) for st, (upd, _wd) in shown.items() if upd.replace(".", "", 1).isdigit()}
        checkpoint()
    # 3. the modules and the submodules, station by station, against ONE read-back of the saved project: what a
    # clone inherited or an earlier run set is left alone (the modules there, the port types equal, the parameter
    # records equal to their oracles); only the rest opens a dialog
    if not saved:
        checkpoint()
    saved_now = {dev.device_no.lower(): dev for dev in read_project(xml).devices}
    for s in (todo if update else h.stations):
        station = s["station_name"]
        if apply_station(d, h, station, saved_now.get(station.lower()), plugged):
            checkpoint()
    # 4. the controller's Auto addressing and the two exports beside the project, as the user does them (recorded
    # 2026-10-24 19:11): HilscherIO.xml (the process data, the IO driver's input) in the project's folder and
    # nWid\config.nxd (the configuration database) - the production folder's layout
    if d.set_auto_addressing(True):
        checkpoint()
    project_dir = os.path.dirname(out_spj)
    process_xml = d.export_process_data(os.path.join(project_dir, "HilscherIO.xml"))
    config_nxd = d.export_configuration(os.path.join(project_dir, "nWid", "config.nxd"))
    for name in sorted(os.listdir(NWID_ASSETS)) if os.path.isdir(NWID_ASSETS) else []:
        shutil.copy2(os.path.join(NWID_ASSETS, name), os.path.join(project_dir, "nWid", name))
        log("  shipped nWid\\%s" % name)
    time.sleep(2.0)
    # the canvas (symbolic names, positions) is written into the XML with the project CLOSED, then read back
    log("close:", d.close())
    canvas.apply_layout(xml, h, only={s["station_name"] for s in todo} if update else None)
    project = read_project(xml)
    v = verify(h, project, plugged, timing_set, skipped=done_names if update else None, keep_extras=update)
    verify_exports(v, h, process_xml, config_nxd, controller_kept=controller_kept)
    return v, xml, plugged, d


def verify_exports(v, handoff, process_xml, config_nxd, controller_kept=False):
    """The process-data export lists the controller under the table's name of station (`controller_kept`: under
    any name - an update left it as it was) and every station of the table (by name of station); the nxd exists."""
    ctrl, devices = exports.process_data_devices(process_xml)
    want = handoff.controller["station_name"]
    if controller_kept:
        v.check(bool(ctrl), "process data export: controller %r" % ctrl)
    else:
        v.check(bool(ctrl) and exports.station_of(ctrl).lower() == want.lower(),
                "process data export: controller named %s (read %r)" % (want, exports.station_of(ctrl)))
    listed = {exports.station_of(name).lower() for name in devices}
    for s in handoff.stations:
        v.check(s["station_name"].lower() in listed, "process data export lists %s" % s["station_name"])
    # the DBM/nxd export writes TWO files (user 2026-10-24: "the sycon export DBM/NXD function exports 2 files. i name
    # them config or c, one has to be renamed"): config.nxd and config_nwid.nxd - UpdateCardV5.bat renames the second
    # to nwid.nxd when it copies them into the card
    for path in (config_nxd, config_nxd[:-4] + "_nwid.nxd"):
        v.check(os.path.exists(path) and os.path.getsize(path) > 0,
                "configuration export %s (%d bytes)" % (os.path.basename(path), os.path.getsize(path) if os.path.exists(path) else 0))
