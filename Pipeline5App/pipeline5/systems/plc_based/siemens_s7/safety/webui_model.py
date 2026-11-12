"""Phase 650 - the plant model of the safety web diagnosis app (C-050): `plant.json`, schema 1.

`build_plant` is PURE: it reads the staged + built SSOT tables (`signals`, `db_members`, `diagnosis_entries`,
`diagnosis_cabinets`, `areas`, `interfaces`, `interface_elements`) and the webui config (device_kinds.csv,
member_states.csv, webui_params.yaml - loaded by the caller) and returns (plant, findings). Nothing here knows a
device kind, a DB or a member name: they all come from the config, so a new kind is one device_kinds.csv row.

- **Entities.** A signal's kind = the first enabled kind (by order) whose family is the signal's object family
  (`classification/object_families.csv`, `type_families.family_for`) and whose types (blank = the family's
  member types) the script type equals or starts with. A family kind groups its signals by index into ONE device
  (`<kind>-<index>`: the e-stop and its lamp, a door's DI/DD/DR/DL/DQ/DO rows, a contactor's KQ and KI); the
  anchor type (blank = the family's) gives its FLD, description and place. A kind without a family (the PROFINET
  nodes, types PA) makes one entity per signal. Kinds whose `state` is `node` are the nodes; the rest devices.
- **Members.** A `db_members` row belongs to what its `source` names: a signal uid (a device's or a node's
  members), an area name (05_EM_STATE / 02_COM), a sorter index, a PROFINET name (99_Commissioning's
  NodesNotInstalled). member_states.csv labels them: a row's pattern ({area} {index} {node} {fld} {n} =
  anything) matched against the members of its DB and scope gives label, role, severity and the `healthy`
  polarity (blank = unknown, shown neutral, one INFO); an entity's member no row matches is listed as a detail.
- **Cabinets.** Every cabinet with a numeric (cabinet, bit) entry: its words (the 620 instance names =
  its DiagnosticTags members, `opc_diagnosis_scl.cabinet_word`), tristate by the 620 rule, its bits with the
  DiagList text and the device or node they belong to.
- **Node failed.** A device's diagnosis entries name their node in `fl_value` (the node's PROFINET_NODES_ALARM
  binding = the PA signal's `plc_binding`): the device lists those node ids, so the page shows it "unknown - node
  failed" while one of them is down.
- **Poll set.** The exact quoted variables read every cycle: the cabinets' words, then the area and sorter
  members. A device's or node's own members are read only while its detail panel is open.
- **Sorters.** A sorter (05_EM_STATE SORTER_nn_NOT_RUNNING, source = its index) belongs to the n-th sorter
  area (areas.csv `sorter`, by order) - the C-040 ordinal rule.

The caller (src://pipeline5/systems/plc_based/siemens_s7/safety/webui_project.py) adds the meta, the PLC, the
measured drawing and writes the folder.
"""
from __future__ import annotations

import json
import re

from pipeline5.findings.finding import Finding
from pipeline5.phases.diagnosis.builder import _int_or_none
from pipeline5.phases.fillout import type_families

PHASE = 650
SCHEMA = 1
SEED = "seed"                          # db_members.source of the generation's seed members (AlwaysTRUE & co.)
_PLACEHOLDER = re.compile(r"\{[A-Za-z_]+\}")
_UNRATED_ORDER = 1000                  # members no member_states row labels: after the labelled ones


def _f(type: str, severity: str, detail: str, location: str = "") -> Finding:
    return Finding(phase=PHASE, type=type, severity=severity, detail=detail, location=location)


def _rows(database, table: str) -> list:
    return list(database[table]) if table in database else []


def _text(value) -> str:
    return "" if value is None else str(value).strip()


def _truthy(value) -> bool:
    return value is True or _text(value).lower() in ("true", "1", "yes")


def _listish(value) -> list:
    """A list cell as staged (a list) or as saved (its JSON text); blank = []."""
    if isinstance(value, (list, tuple)):
        return [_text(v) for v in value if _text(v)]
    text = _text(value)
    if not text:
        return []
    if text.startswith("["):
        try:
            return [_text(v) for v in json.loads(text) if _text(v)]
        except ValueError:
            pass
    return [part.strip() for part in text.split("|") if part.strip()]


def _mapping(value) -> dict:
    if isinstance(value, dict):
        return value
    try:
        out = json.loads(_text(value) or "{}")
    except ValueError:
        return {}
    return out if isinstance(out, dict) else {}


def quote(*parts: str) -> str:
    """The Web API variable name: each part double-quoted, dot-joined (the TIA notation of symbols.TiaSymbols,
    one level per struct)."""
    return ".".join(f'"{part}"' for part in parts if part)


def member_name(row: dict) -> str:
    """A db_members row's name inside its DB: `<struct>.<member>` when it sits in a struct."""
    struct = _text(row.get("struct"))
    return f"{struct}.{_text(row.get('member'))}" if struct else _text(row.get("member"))


def member_var(row: dict) -> str:
    return quote(_text(row.get("db_name")), _text(row.get("struct")), _text(row.get("member")))


def member_pattern(template: str) -> re.Pattern:
    """A member_states.csv `member` pattern as an anchored regex: each {placeholder} = one or more characters."""
    parts = _PLACEHOLDER.split(template)
    return re.compile("^" + "(?:.+?)".join(re.escape(p) for p in parts) + "$")


def _member(row: dict, rule: dict | None = None) -> dict:
    if rule is None:
        return {"var": member_var(row), "db": _text(row.get("db_name")), "member": member_name(row),
                "label": member_name(row), "healthy": None, "severity": "info", "role": "detail",
                "order": _UNRATED_ORDER, "labelled": False}
    return {"var": member_var(row), "db": _text(row.get("db_name")), "member": member_name(row),
            "label": rule["label"], "healthy": rule["healthy"], "severity": rule["severity"], "role": rule["role"],
            "order": rule["order"], "labelled": True}


def _scope_index(member_states: list, members_by_db: dict) -> dict:
    """{scope: {source: [labelled member]}} - every member_states row matched against its DB's members. A member
    several rows of one scope match takes the most specific one (the most literal characters - `Safety Encoder
    {n} Sensor 1 Healthy` before `Safety Encoder {n} Healthy`), then the lower order, then the file order."""
    best = {}
    for pos, rule in enumerate(member_states):
        rx = member_pattern(rule["member"])
        rank = (-len(_PLACEHOLDER.sub("", rule["member"])), rule["order"], pos)
        for row in members_by_db.get(rule["db_name"], []):
            if rx.match(member_name(row)):
                key = (rule["scope"], member_var(row))
                if key not in best or rank < best[key][0]:
                    best[key] = (rank, rule, row)
    index: dict = {}
    for (scope, _var), (_rank, rule, row) in sorted(best.items(), key=lambda kv: kv[1][0][1:]):
        index.setdefault(scope, {}).setdefault(_text(row.get("source")), []).append(_member(row, rule))
    return index


def _members_of(keys, scope: str, scope_index: dict, members_by_source: dict) -> list:
    """An entity's members: every db_members row whose source is one of `keys`, labelled by its scope's
    member_states rows where one matches (labelled first, in rule order), the rest as details."""
    labelled = {}
    for key in keys:
        for m in scope_index.get(scope, {}).get(key, []):
            labelled.setdefault(m["var"], m)
    out, seen = [], set()
    for key in keys:
        for row in members_by_source.get(key, []):
            var = member_var(row)
            if var not in seen:
                seen.add(var)
                out.append(labelled.get(var) or _member(row))
    return sorted(out, key=lambda m: m["order"])


def _public(member: dict) -> dict:
    return {k: member[k] for k in ("var", "label", "healthy", "severity", "role")}


def _type_matches(script_type: str, types) -> bool:
    st = script_type.upper()
    return any(st == t.upper() or st.startswith(t.upper()) for t in types if t)


def _kind_of(script_type: str, kinds: list, families: list):
    fam = type_families.family_for(script_type, families)
    for kind in kinds:
        if kind["family"]:
            if fam is None or fam.family != kind["family"]:
                continue
            types = kind["types"] or list(fam.member_types)
        else:
            types = kind["types"]
        if types and _type_matches(script_type, types):
            return kind, fam
    return None, fam


def _anchor(signals: list, anchors: list) -> dict:
    """The entity's anchor signal: an exact anchor type first (in the anchors' order), then a type starting
    with one, else the first signal."""
    types = [_text(s.get("script_type")).upper() for s in signals]
    for anchor in anchors:
        for st, s in zip(types, signals):
            if st == anchor.upper():
                return s
    for anchor in anchors:
        for st, s in zip(types, signals):
            if st.startswith(anchor.upper()):
                return s
    return signals[0]


def _fld(signal: dict) -> str:
    return (_text(signal.get("iol_FLD")) or _text(signal.get("combined_FLD"))
            or "".join(_text(signal.get(k)) for k in ("functional_unit", "location", "device")))


def _description(anchor: dict, signals: list) -> str:
    return _text(anchor.get("desc_l1")) or next((_text(s.get("desc_l1")) for s in signals if _text(s.get("desc_l1"))),
                                                "")


def _entities(signals: list, kinds: list, families: list) -> list:
    """[(kind, family, index-or-key, [signals])] in signal order: one per (kind, index) for a family kind, one
    per signal for a kind without a family."""
    groups: dict = {}
    order = []
    for s in signals:
        st = _text(s.get("script_type"))
        if not st:
            continue
        kind, fam = _kind_of(st, kinds, families)
        if kind is None:
            continue
        if kind["family"]:
            index = _text(s.get("index"))
            if not index:
                continue
            key = (kind["kind"], index)
        else:
            index = _text(s.get("profinet_name")) or _text(s.get("uid"))
            key = (kind["kind"], index)
        if key not in groups:
            groups[key] = (kind, fam, index, [])
            order.append(key)
        groups[key][3].append(s)
    return [groups[k] for k in order]


def _diag_text(entry: dict) -> str:
    columns = _mapping(entry.get("diag_columns"))
    return _text(columns.get("Diag Desc")) or _text(entry.get("rule_name")) or _text(entry.get("in_binding"))


def _cabinets(database, entries: list, owner_of: dict, member_by_name: dict, diag: dict, tristate: set) -> tuple:
    """(cabinets, missing word names) - every cabinet with a numeric entry, in id order."""
    from pipeline5.systems.plc_based.siemens_s7.safety import opc_diagnosis_scl as opc
    blocks = {}
    for row in _rows(database, "diagnosis_cabinets"):
        cid = _int_or_none(row.get("cabinet_id"))
        if cid is not None:
            blocks[cid] = row
    by_cab: dict = {}
    for e in entries:
        cid, bit = _int_or_none(e.get("cabinet")), _int_or_none(e.get("bit"))
        if cid is not None and bit is not None:
            by_cab.setdefault(cid, []).append((bit, e))
    roles = ["STATE"] + diag["alarm_dwords"] + diag["warning_dwords"]
    out, missing = [], []
    for cid in sorted(by_cab):
        blk = blocks.get(cid, {})
        index = _text(blk.get("index")) or f"{cid:03d}"
        template_type = _int_or_none(blk.get("template_type"))
        words = {}
        for role in roles:
            name = opc.cabinet_word(index, role, diag["instance_template"])
            row = member_by_name.get(name)
            if row is None:
                missing.append(name)
            else:
                words[role] = member_var(row)
        bits = []
        for bit, e in sorted(by_cab[cid], key=lambda be: (be[0], _truthy(be[1].get("is_warning")))):
            owner = owner_of.get(_text(e.get("source_signal")))
            bits.append({"bit": bit, "warning": _truthy(e.get("is_warning")), "text": _diag_text(e),
                         "owner": owner, "source": _text(e.get("source"))})
        out.append({"id": cid, "index": index, "fld": _text(blk.get("fld")) or f"CABINET {index}",
                    "template_type": template_type,
                    "tristate": template_type in (2, 4) or cid in tristate,
                    "words": words, "alarm_words": list(diag["alarm_dwords"]),
                    "warning_words": list(diag["warning_dwords"]), "bits": bits})
    return out, missing


def _diag_pairs(entries: list) -> list:
    pairs = set()
    for e in entries:
        cid, bit = _int_or_none(e.get("cabinet")), _int_or_none(e.get("bit"))
        if cid is not None and bit is not None:
            pairs.add((cid, bit, _truthy(e.get("is_warning"))))
    return [{"cabinet": c, "bit": b, "warning": w} for c, b, w in sorted(pairs)]


def build_plant(database, kinds: list, member_states: list, params: dict, *, positions=(), drawing=None,
                families=None, diag=None, tristate=None, meta=None, plc=None) -> tuple:
    """The plant model (schema 1) and the findings. `database` = the SSOT tables (a Database or a {table: rows}
    mapping); `kinds` / `member_states` / `params` = the loaded webui config; `positions` = the loaded positions
    rows; `drawing` = {file, width, height, view_box} of the measured plant drawing or None; `families` = the
    object families (default: loaded); `diag` = the 620 knobs (default: generation_params.yaml); `tristate` = the
    per-type tristate cabinets (default: the 620 rule over the signals); `meta` / `plc` = the header sections."""
    from pipeline5.systems.plc_based.siemens_s7.safety import opc_diagnosis_scl as opc
    findings = []
    families = type_families.load_object_families() if families is None else families
    diag = opc.diag_params() if diag is None else diag
    tristate = opc.tristate_cabinets(database) if tristate is None else set(tristate)
    enabled = [k for k in kinds if k["enabled"]]
    family_names = {f.family for f in families}
    for kind in enabled:
        if kind["family"] and kind["family"] not in family_names:
            findings.append(_f("webui_kind_family_unknown", "WARN",
                               f"device kind {kind['kind']!r}: family {kind['family']!r} is not in "
                               f"classification/object_families.csv - the kind stays empty", "webui/device_kinds.csv"))

    signals = _rows(database, "signals")
    entries = _rows(database, "diagnosis_entries")
    members = [row for row in _rows(database, "db_members") if _text(row.get("source")) != SEED]
    members_by_db, members_by_source, member_by_name = {}, {}, {}
    for row in members:
        members_by_db.setdefault(_text(row.get("db_name")), []).append(row)
        members_by_source.setdefault(_text(row.get("source")), []).append(row)
        member_by_name.setdefault(member_name(row), row)
    scope_index = _scope_index(member_states, members_by_db)
    entries_by_signal: dict = {}
    for e in entries:
        entries_by_signal.setdefault(_text(e.get("source_signal")), []).append(e)
    area_names = [_text(a.get("name")) for a in sorted(_rows(database, "areas"),
                                                       key=lambda a: _int_or_none(a.get("order")) or 0)]

    # --- the entities ---------------------------------------------------------------------------- #
    nodes, devices, owner_of, node_by_binding, used = [], [], {}, {}, []
    staged = _entities(signals, enabled, families)
    for kind, fam, index, sigs in staged:            # the nodes first: the devices name them
        if kind["state"] != "node":
            continue
        s = sigs[0]
        entity_id = f"{kind['kind']}-{index}"
        keys = [_text(x.get("uid")) for x in sigs] + [_text(s.get("profinet_name"))]
        own = _members_of([k for k in keys if k], "node", scope_index, members_by_source)
        used += own
        node = {"id": entity_id, "kind": kind["kind"], "name": _text(s.get("profinet_name")),
                "ip": _text(s.get("profinet_ip")), "fld": _fld(s), "description": _description(s, sigs),
                "diag": _diag_pairs([e for x in sigs for e in entries_by_signal.get(_text(x.get("uid")), [])]),
                "members": [_public(m) for m in own]}
        nodes.append(node)
        for x in sigs:
            owner_of[_text(x.get("uid"))] = entity_id
            if _text(x.get("plc_binding")):
                node_by_binding[_text(x.get("plc_binding"))] = entity_id
    unresolved = set()
    for kind, fam, index, sigs in staged:
        if kind["state"] == "node":
            continue
        anchors = kind["anchor_types"] or ([a for a in fam.anchor.split("|") if a] if fam else [])
        anchor = _anchor(sigs, anchors)
        entity_id = f"{kind['kind']}-{index}"
        uids = [_text(x.get("uid")) for x in sigs]
        own_entries = [e for uid in uids for e in entries_by_signal.get(uid, [])]
        node_ids = []
        for e in own_entries:
            binding = _text(e.get("fl_value"))
            if not binding or binding.lower() in ("true", "false"):
                continue
            node_id = node_by_binding.get(binding)
            if node_id is None:
                unresolved.add(binding)
            elif node_id not in node_ids:
                node_ids.append(node_id)
        areas = []
        for x in sigs:
            for area in _listish(x.get("matrix_areas")):
                if area not in areas:
                    areas.append(area)
        areas = [a for a in area_names if a in areas] + [a for a in areas if a not in area_names]
        own = _members_of(uids, "device", scope_index, members_by_source)
        used += own
        tags = [{"var": quote(_text(x.get("name_in_tagtable"))), "type": _text(x.get("script_type")),
                 "address": _text(x.get("bit")), "table": _text(x.get("tagtable"))}     # the label = var unquoted
                for x in sigs if _text(x.get("name_in_tagtable"))]
        devices.append({"id": entity_id, "kind": kind["kind"], "index": index, "fld": _fld(anchor),
                        "functional_unit": _text(anchor.get("functional_unit")),
                        "location": _text(anchor.get("location")), "device": _text(anchor.get("device")),
                        "description": _description(anchor, sigs), "areas": areas, "diag": _diag_pairs(own_entries),
                        "nodes": node_ids,
                        "members": [_public(m) for m in own],
                        "tags": tags})
        for uid in uids:
            owner_of.setdefault(uid, entity_id)
    if unresolved:
        findings.append(_f("webui_node_unresolved", "WARN",
                           f"{len(unresolved)} node binding(s) in diagnosis_entries.fl_value name no PROFINET node "
                           f"of the page (their devices never show 'node failed'): {', '.join(sorted(unresolved)[:5])}",
                           "diagnosis_entries"))

    # --- the cabinets, areas, sorters, interfaces ------------------------------------------------ #
    cabinets, missing = _cabinets(database, entries, owner_of, member_by_name, diag, tristate)
    if missing:
        findings.append(_f("webui_cabinet_word_missing", "WARN",
                           f"{len(missing)} cabinet word(s) are no db_members row - not read: {', '.join(missing[:5])}",
                           "db_members"))
    sorter_keys = sorted(scope_index.get("sorter", {}))
    sorter_areas = [_text(a.get("name")) for a in sorted(_rows(database, "areas"),
                                                         key=lambda a: _int_or_none(a.get("order")) or 0)
                    if _truthy(a.get("sorter"))]
    sorters = [{"id": f"sorter-{key}", "index": key,
                "area": sorter_areas[n] if n < len(sorter_areas) else None,
                "members": [_public(m) for m in sorted(scope_index["sorter"][key], key=lambda m: m["order"])]}
               for n, key in enumerate(sorter_keys)]
    if sorters and len(sorter_keys) != len(sorter_areas):
        findings.append(_f("webui_sorter_unlinked", "INFO",
                           f"{len(sorter_keys)} sorter(s) but {len(sorter_areas)} sorter area(s) in areas.csv - "
                           f"linked by ordinal as far as both go", "areas"))
    sorter_of_area = {s["area"]: s["id"] for s in sorters if s["area"]}
    areas = []
    for a in sorted(_rows(database, "areas"), key=lambda a: _int_or_none(a.get("order")) or 0):
        name = _text(a.get("name"))
        areas.append({"id": name, "name": name, "number": _text(a.get("number")), "parent": _text(a.get("parent")) or None,
                      "part": _text(a.get("part")), "order": _int_or_none(a.get("order")),
                      "description": _text(a.get("description")), "sorter": sorter_of_area.get(name),
                      "members": [_public(m) for m in sorted(scope_index.get("area", {}).get(name, []),
                                                              key=lambda m: m["order"])]})
    elements_by_interface: dict = {}
    for el in _rows(database, "interface_elements"):
        if _text(el.get("signal_name")):
            elements_by_interface.setdefault(_text(el.get("interface")), []).append(
                {"var": quote(_text(el.get("signal_name"))), "label": _text(el.get("signal_name")),
                 "description": _text(el.get("description")), "category": _text(el.get("category")),
                 "direction": _text(el.get("direction")), "data_type": _text(el.get("data_type")),
                 "address": _text(el.get("io_address_side1"))})
    interfaces = [{"id": _text(i.get("instance")), "description": _text(i.get("description")),
                   "machine_type": _text(i.get("machine_type")), "device": _text(i.get("device")),
                   "diag": _truthy(i.get("is_diag")),
                   "elements": elements_by_interface.get(_text(i.get("instance")), [])}
                  for i in _rows(database, "interfaces")]

    # --- the poll set, the layout ----------------------------------------------------------------- #
    poll, seen = [], set()

    def add(var):
        if var and var not in seen:
            seen.add(var)
            poll.append(var)
    for cab in cabinets:
        for role in ["STATE"] + cab["alarm_words"] + cab["warning_words"]:
            add(cab["words"].get(role))
    for area in areas:
        for m in area["members"]:
            add(m["var"])
    for sorter in sorters:
        for m in sorter["members"]:
            add(m["var"])

    known = {f"{e['kind']}|{e['fld']}" for e in devices + nodes}
    placed = {}
    for row in positions:
        placed[f"{row['kind']}|{row['fld']}"] = [row["x"], row["y"]]
    stale = sorted(k for k in placed if k not in known)
    if stale:
        findings.append(_f("webui_position_stale", "WARN",
                           f"{len(stale)} position(s) name no device of the plant - ignored by the page: "
                           f"{', '.join(stale[:5])}", params["layout"]["positions"]))
    if drawing is not None:
        unplaced = len(known - set(placed))
        if unplaced:
            findings.append(_f("webui_unplaced", "INFO",
                               f"{unplaced} of {len(known)} device(s) have no position on the plant drawing - the "
                               f"page lists them in its edit mode's tray", params["layout"]["positions"]))

    rated = [m for m in used if m["labelled"]]
    rated += [m for name in area_names for m in scope_index.get("area", {}).get(name, [])]
    rated += [m for key in sorter_keys for m in scope_index["sorter"][key]]
    unrated = sum(1 for m in rated if m["healthy"] is None)
    if unrated:
        findings.append(_f("webui_polarity_unknown", "INFO",
                           f"{unrated} of {len(rated)} labelled member(s) have no healthy polarity in "
                           f"member_states.csv - the page shows them neutral", "webui/member_states.csv"))
    if params["diag"]["alarm_bit"] is None or params["diag"]["warning_bit"] is None:
        findings.append(_f("webui_diag_polarity_unknown", "INFO",
                           "diag.alarm_bit / warning_bit unknown in webui_params.yaml - the cabinet bits are shown "
                           "neutral", "webui/webui_params.yaml"))
    counts = {k["kind"]: 0 for k in enabled}
    for e in devices + nodes:
        counts[e["kind"]] += 1
    for kind in enabled:
        if counts[kind["kind"]] == 0:
            findings.append(_f("webui_kind_empty", "INFO", f"device kind {kind['kind']!r}: no signal of the project "
                                                           f"is one - the page shows the kind empty",
                               "webui/device_kinds.csv"))

    app = params["app"]
    plant = {
        "schema": SCHEMA, "meta": dict(meta or {}), "plc": dict(plc or {}),
        "app": {"name": app["name"], "title": app["title"]},
        "polling": dict(params["polling"]), "login": {"users": list(params["login"]["users"])},
        "diag": dict(params["diag"]),
        "kinds": [{k: kind[k] for k in ("kind", "label", "plural", "icon", "order", "state", "group_by")}
                  for kind in enabled],
        "poll": poll, "areas": areas, "sorters": sorters, "cabinets": cabinets, "nodes": nodes, "devices": devices,
        "interfaces": interfaces,
        "layout": {"image": drawing, "positions": placed, "group_by": list(params["layout"]["group_by"])},
        "custom_data": dict(params["custom_data"]),
    }
    plant["counts"] = {"kinds": counts, "areas": len(areas), "sorters": len(sorters), "cabinets": len(cabinets),
                       "interfaces": len(interfaces), "poll": len(poll)}
    return plant, findings


def to_json(plant: dict) -> bytes:
    """plant.json's bytes: compact UTF-8 JSON (the page parses it once), a trailing newline."""
    return (json.dumps(plant, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
