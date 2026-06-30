"""Turn matched pairs into the classified quality picture.

The two load-bearing ideas (both evidence-derived):
  1. NET OUT systematic re-schemes. A wholesale address re-map / re-slot / re-pin / device-tag rename
     touches hundreds of rows but is a handful of deliberate operations. Such field-changes are detected
     (byte-level address bijection, low-cardinality value bijection, or the wiring-matched T3 rename) and
     EXCLUDED from the genuine-defect count - reported instead as their own re-scheme events. The single
     row that breaks a systematic pattern (an I<->Q address-prefix flip) stays a GENUINE critical defect.
  2. Tag every correction by DIRECTION - gap-fill (blank->value), value-change, or value-loss
     (value->blank, the "got worse" regression class) - and weight it by the highest tier it touches.
Channel-uncertain (T2pos) genuine corrections are AGGREGATED to one block-level change (the per-channel
attribution is not provable). Added rows are split node-aware into upgrade blocks vs forgotten signals.
"""
from __future__ import annotations

import re
from collections import defaultdict

from pipeline4.domain.changes.match import norm, fld, desc

TIER_RANK = {"minor": 1, "major": 2, "critical": 3}
_MIN_SYSTEMATIC = 8          # a field needs at least this many changed rows to be a "systematic" event
_UPGRADE_BLOCK = 4           # an added contiguous block this size (or larger) reads as an upgrade


def _bucket(tier: str) -> str:
    """Clamp a (possibly hand-edited / typo'd) tier to a known by_tier bucket - change_weights.csv is
    hand-editable, so an unknown tier must not KeyError the whole report."""
    return tier if tier in ("critical", "major", "minor") else "minor"


def _tier(weights: dict, field: str) -> str:
    return weights.get(field, "minor")


def _live_fields(weights: dict, sample_row: dict) -> list:
    """The compared fields: every non-provenance key present on the row, minus the `exclude`-tier
    (dead/never-authored) columns."""
    return [k for k in sample_row
            if not k.startswith("_") and k != "effects" and _tier(weights, k) != "exclude"]


def _direction(old_value, new_value) -> str:
    o, n = norm(old_value), norm(new_value)
    if o and not n:
        return "value-loss"
    if not o and n:
        return "gap-fill"
    return "value-change"


def _lev_le1(a: str, b: str) -> bool:
    """True when the Levenshtein distance between `a` and `b` is <= 1 (one insert/delete/substitute)."""
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    i = 0
    while i < min(la, lb) and a[i] == b[i]:
        i += 1
    if la == lb:
        return a[i + 1:] == b[i + 1:]                      # substitution
    if la > lb:
        return a[i + 1:] == b[i:]                          # deletion from a
    return a[i:] == b[i + 1:]                              # insertion into a


def _fld_noise(old, new) -> bool:
    """A FLD value change is NOISE when - after dropping every non-alphanumeric char - the two values
    differ by AT MOST ONE alphanumeric character. So a punctuation/whitespace-only change (e.g. a stray
    text-guard apostrophe `-'Q66305 -> -Q66305`) or a single-char typo/renumber. Operator's rule, applied
    ONLY to the FLD fields."""
    ao = re.sub(r"[^a-z0-9]", "", str(old or "").lower())
    an = re.sub(r"[^a-z0-9]", "", str(new or "").lower())
    return _lev_le1(ao, an)


_ADDR = re.compile(r"^([A-Za-z]+)\s*(\d+)(?:\.(\d+))?$")


def _parse_addr(value):
    m = _ADDR.match(norm(value))
    if not m:
        return None
    return m.group(1), int(m.group(2)), (int(m.group(3)) if m.group(3) is not None else None)


def detect_address_event(changes: list) -> dict | None:
    """`changes` = list of (old, new). An address re-map is systematic when, among the same-prefix
    changes, the old-byte -> new-byte map is near-bijective (<=10% multi-target). Returns the event
    (with a `member` predicate set) or None. Prefix-flipping rows (I<->Q) are NEVER members - they stay
    genuine defects."""
    parsed = [(p_o, p_n) for p_o, p_n in ((_parse_addr(o), _parse_addr(n)) for o, n in changes) if p_o and p_n]
    same_prefix = [(o, n) for o, n in parsed if o[0] == n[0]]
    if len(same_prefix) < _MIN_SYSTEMATIC:
        return None
    by_old_byte = defaultdict(set)
    for o, n in same_prefix:
        by_old_byte[(o[0], o[1])].add(n[1])
    multi = sum(1 for targets in by_old_byte.values() if len(targets) > 1)
    if multi > max(1, len(by_old_byte) * 0.1):
        return None
    byte_map = {k: next(iter(v)) for k, v in by_old_byte.items()}

    def member(old_value, new_value) -> bool:
        po, pn = _parse_addr(old_value), _parse_addr(new_value)
        if not po or not pn or po[0] != pn[0]:        # prefix flip (I<->Q) is NOT systematic
            return False
        return byte_map.get((po[0], po[1])) == pn[1]

    return {"kind": "address", "rows": len(same_prefix), "byte_rules": len(byte_map),
            "summary": f"address re-map across {len(byte_map)} byte-blocks ({len(same_prefix)} rows)",
            "sample": [f"{o}->{n}" for o, n in changes[:6]], "member": member}


def detect_value_event(changes: list) -> dict | None:
    """A low-cardinality re-map (re-slot / re-pin / re-key): few distinct (old->new) pairs over many
    rows, near-bijective on the old value. Returns the event or None."""
    if len(changes) < _MIN_SYSTEMATIC:
        return None
    pairs = [(norm(o), norm(n)) for o, n in changes]
    distinct = set(pairs)
    if len(distinct) > max(3, len(pairs) * 0.35):
        return None
    by_old = defaultdict(set)
    for o, n in pairs:
        by_old[o].add(n)
    if sum(1 for v in by_old.values() if len(v) > 1) > max(1, len(by_old) * 0.1):
        return None
    member_set = distinct

    def member(old_value, new_value) -> bool:
        return (norm(old_value), norm(new_value)) in member_set

    return {"kind": "value", "rows": len(pairs), "distinct": len(distinct),
            "summary": f"{len(distinct)} value re-maps over {len(pairs)} rows",
            "sample": [f"{o}->{n}" for o, n in sorted(distinct)[:6]], "member": member}


# Systematic re-schemes are MECHANICAL bulk operations on STRUCTURAL fields only. A change to a semantic
# field (type, normal_condition, descriptions, ts_ref, mnemonic) is ALWAYS a real authoring decision -
# even when many rows share a value - so those fields are never collapsed into a "re-scheme" event.
_ADDR_FIELDS = {"bit", "address", "digital_output"}
_RESCHEME_FIELDS = {"slot", "pin_no", "connector"}
_RENAME_FIELDS = {"device", "functional_unit", "location"}
# Structural fields whose changes are GROUPED BY NODE and COUNTED (never hidden) - a re-addressing /
# re-slot / re-pin is the costliest correction to apply on a built machine, so it is surfaced; grouping
# by node only tames the per-row noise. A bulk device-tag rename also groups (handled via __rename__).
_GROUP_BY_NODE = _ADDR_FIELDS | _RESCHEME_FIELDS


def _detect_systematic(pairs: list, fields: list, weights: dict) -> dict:
    """Per STRUCTURAL field, detect a systematic event over the corrected pairs. `device/functional_unit/
    location` changes on a T3 pair (matched by stable wiring despite fld drift) are the device-tag RENAME
    event. Returns {field -> event} where each event has a `member(old,new)` predicate + a label."""
    events: dict = {}
    rename_rows = 0
    for field in fields:
        if field in _RENAME_FIELDS:
            rename_rows = max(rename_rows, sum(
                1 for p in pairs if p.get("tier") == "T3"
                and norm(p["old"].get(field)) != norm(p["new"].get(field))))
            continue
        if field not in _ADDR_FIELDS and field not in _RESCHEME_FIELDS:
            continue                                          # semantic field - never a re-scheme
        changes = [(p["old"].get(field), p["new"].get(field)) for p in pairs
                   if norm(p["old"].get(field)) != norm(p["new"].get(field))]
        event = detect_address_event(changes) if field in _ADDR_FIELDS else detect_value_event(changes)
        if event:
            event["field"], event["tier"] = field, _tier(weights, field)
            event["label"] = _EVENT_LABELS.get(field, f"{field} re-map")
            events[field] = event
    if rename_rows >= _MIN_SYSTEMATIC:
        events["__rename__"] = {"kind": "rename", "field": "device", "rows": rename_rows,
                                "tier": "critical", "label": "device-tag rename (matched by wiring)",
                                "summary": f"device tag re-keyed on {rename_rows} rows (K->Q / range notation)",
                                "sample": [], "member": lambda o, n: False}
    return events


_EVENT_LABELS = {"bit": "I/O address re-map", "slot": "module re-slot", "pin_no": "connector re-pin",
                 "connector": "connector re-wire", "address": "C&E address re-map",
                 "digital_output": "AREA address re-map"}


def _is_rename_pair(pair: dict, field: str) -> bool:
    return pair.get("tier") == "T3" and field in ("device", "functional_unit", "location")


def classify_iolist(match_result: dict, weights: dict) -> dict:
    """Classify the I/O List pairs + added/removed into the quality picture.

    STRUCTURAL / re-scheme fields (I/O address `bit`, slot, pin, connector, + a bulk device-tag rename)
    are GROUPED BY NODE and COUNTED at the field's weight - never hidden. A re-addressing is the costliest
    correction to apply on a built machine (re-read manuals, re-test, propagate to many devices), so it is
    surfaced; grouping by node only tames the per-row noise. Other (semantic) field changes are itemized
    per row. Every changed row is bucketed ONCE by its highest-tier change (so an address-only row reads
    critical). The coordinated-re-map detection survives only as context, never as a reason to hide."""
    pairs = match_result["pairs"]
    sample = pairs[0]["old"] if pairs else {}
    fields = _live_fields(weights, sample)
    events = _detect_systematic(pairs, fields, weights)   # coordinated-re-map context + the bulk-rename flag
    bulk_rename = bool(events.get("__rename__"))

    # NO-DESCRIPTION rows = unused channels (nothing wired) - kept OUT of the defect analysis:
    #   unchanged -> `unused` (grey); changed -> `complementary` review (2nd grey) - a re-addressed free
    #   slot is not a defect today, but if a signal is wired into it later a wrong address reproduces the
    #   original mistake, so it is tracked for review (the operator's call).
    intact = changed = unused = complementary = 0
    corrections: list = []           # itemized corrections on REAL signals (each carries its `confidence`)
    complementary_entries: list = []  # changes on no-description (unused) rows
    noise_entries: list = []         # FLD-only changes that are noise (punctuation / <=1 alphanumeric char)
    by_tier = {"critical": 0, "major": 0, "minor": 0}
    by_direction = {"gap-fill": 0, "value-change": 0, "value-loss": 0}
    struct: dict = defaultdict(int)          # (node, field) -> changed-row count (structural / re-scheme)
    struct_tier: dict = {}
    struct_detail: dict = defaultdict(list)  # (node, field) -> [(old, new), ...] the actual values changed

    def _grouped(field: str) -> bool:
        return field in _GROUP_BY_NODE or (field in _RENAME_FIELDS and bulk_rename)

    for pair in pairs:
        old, new = pair["old"], pair["new"]
        node = old.get("_node", "")
        changed_fields = [f for f in fields if norm(old.get(f)) != norm(new.get(f))]
        has_desc = bool(norm(old.get("desc_l1")) or norm(old.get("desc_l1b")))
        if not has_desc:                                      # an unused channel - out of the defect analysis
            if not changed_fields:
                unused += 1
            else:
                complementary += 1
                comp_diffs = [{"field": f, "old": old.get(f, ""), "new": new.get(f, ""),
                               "tier": _tier(weights, f), "direction": _direction(old.get(f), new.get(f))}
                              for f in changed_fields]
                complementary_entries.append({
                    "node": node, "fld": fld(old), "desc": "", "diffs": comp_diffs,
                    "tier": max((d["tier"] for d in comp_diffs), key=lambda t: TIER_RANK.get(t, 1)),
                    "directions": sorted({d["direction"] for d in comp_diffs}),
                    "regression": False, "confidence": pair["confidence"]})
            continue
        if not changed_fields:
            intact += 1
            continue
        changed += 1
        itemized = []
        for f in changed_fields:
            if _grouped(f):
                struct[(node, f)] += 1
                struct_tier[f] = _tier(weights, f)
                struct_detail[(node, f)].append((str(old.get(f, "")), str(new.get(f, ""))))
            else:
                itemized.append(f)
        # every changed row is bucketed ONCE, by the max tier across ALL its changes (grouped + itemized).
        row_tier = max((_tier(weights, f) for f in changed_fields), key=lambda t: TIER_RANK.get(t, 1))
        by_tier[_bucket(row_tier)] += 1
        if not itemized:
            continue                              # a structural-only row is counted in `struct` + by_tier
        diffs = [{"field": f, "old": old.get(f, ""), "new": new.get(f, ""),
                  "tier": _tier(weights, f), "direction": _direction(old.get(f), new.get(f))}
                 for f in itemized]
        for d in diffs:
            by_direction[d["direction"]] += 1
        item_tier = max((d["tier"] for d in diffs), key=lambda t: TIER_RANK.get(t, 1))
        regression = any(d["direction"] == "value-loss" and d["tier"] in ("critical", "major") for d in diffs)
        entry = {"node": node, "sheet": old.get("_sheet"), "row_old": old.get("_row"),
                 "row_new": new.get("_row"), "fld": fld(old), "desc": desc(old).replace("|", " ").strip(),
                 "diffs": diffs, "tier": item_tier, "directions": sorted({d["direction"] for d in diffs}),
                 "regression": regression, "confidence": pair["confidence"]}
        # NOISE (operator's rule): a row whose itemized changes are ALL FLD and each is noise (punctuation /
        # <=1 alphanumeric char). Broken out into its own listing only - the severity counts are unchanged.
        if all(f in _RENAME_FIELDS and _fld_noise(old.get(f), new.get(f)) for f in itemized):
            noise_entries.append(entry)
        else:
            corrections.append(entry)

    correction_blocks = _aggregate_by_node(corrections)       # all itemized, grouped per node (confidence per block)
    complementary_blocks = _aggregate_by_node(complementary_entries)   # unused-channel changes, grouped per node
    noise_blocks = _aggregate_by_node(noise_entries)          # FLD noise (punctuation / 1-char), grouped per node
    grouped_changes = [{"node": n, "field": f, "count": c, "tier": struct_tier[f],
                        "label": _EVENT_LABELS.get(f, f), "changes": struct_detail[(n, f)]}
                       for (n, f), c in struct.items()]
    grouped_changes.sort(key=lambda g: (-TIER_RANK.get(g["tier"], 1), -g["count"]))
    structural: dict = {}                        # per-field rollup: address X rows across Y nodes
    for (n, f), c in struct.items():
        s = structural.setdefault(f, {"field": f, "label": _EVENT_LABELS.get(f, f),
                                      "tier": struct_tier[f], "rows": 0, "nodes": 0})
        s["rows"] += c
        s["nodes"] += 1
    structural_list = sorted(structural.values(), key=lambda s: (-TIER_RANK.get(s["tier"], 1), -s["rows"]))

    upgrades, forgotten, review = _classify_added(match_result["added"])
    return {
        "matched": len(pairs), "intact": intact, "unused": unused, "changed": changed,
        "complementary": complementary, "complementary_blocks": complementary_blocks,
        "removed": [_row_brief(r) for r in match_result["removed"]],
        "corrections": corrections, "correction_count": len(corrections),
        "correction_blocks": correction_blocks, "noise_blocks": noise_blocks,
        "by_tier": by_tier, "by_direction": by_direction,
        "regressions": [c for c in corrections if c["regression"]],
        "grouped_changes": grouped_changes, "structural": structural_list,
        "structural_rows": sum(struct.values()),
        "systematic_events": [_event_brief(e) for e in events.values()],
        "upgrades": upgrades, "upgrade_rows": sum(u["count"] for u in upgrades),
        "forgotten": forgotten, "review_clusters": review,
        "added_total": len(match_result["added"]),
    }


def _aggregate_by_node(entries: list) -> list:
    """Aggregate itemized correction entries into ONE block PER NODE (the per-device rows collapse). Each
    block carries WHAT changed across the whole node: per field the old->new values across ALL the node's
    rows, the field tier, and the direction(s) (gap-fill / value-change / value-loss). `devices` = how many
    distinct devices (flds) contributed; `confidence` is channel-uncertain when any member row is."""
    grp = defaultdict(list)
    for e in entries:
        grp[e["node"]].append(e)
    blocks = []
    for node, members in grp.items():
        tier = max((m["tier"] for m in members), key=lambda t: TIER_RANK.get(t, 1))
        flds = sorted({m["fld"] for m in members})
        by_field: dict = defaultdict(list)            # field -> [(old, new), ...] across the node's rows
        field_tier: dict = {}
        field_dirs: dict = defaultdict(set)
        for m in members:
            for d in m["diffs"]:
                by_field[d["field"]].append((d["old"], d["new"]))
                field_tier[d["field"]] = d["tier"]
                field_dirs[d["field"]].add(d["direction"])
        fields = sorted(({"field": f, "tier": field_tier[f], "directions": sorted(field_dirs[f]),
                          "values": vals} for f, vals in by_field.items()),
                        key=lambda x: -TIER_RANK.get(x["tier"], 1))
        single = len(flds) == 1
        desc = next((m["desc"] for m in members if m["desc"]), "") if single else ""
        confidence = "channel-uncertain" if any(m.get("confidence") == "channel-uncertain"
                                                for m in members) else "high"
        blocks.append({"node": node, "fld": flds[0] if single else "", "devices": len(flds),
                       "count": len(members), "channels": len(members), "tier": tier,
                       "desc": desc, "fields": fields, "confidence": confidence})
    return blocks


def _added_detail(rows: list) -> list:
    """The involved added rows as [{desc, fld, address}] - only rows WITH a description (the empty spacer
    rows are layout, not signals). `fld` is the as-authored FU+LOC+DEV tag; `address` is the I/O bit."""
    out = []
    for r in rows:
        d = desc(r).replace("|", " ").strip()
        if not d:
            continue
        out.append({"desc": d,
                    "fld": (str(r.get("functional_unit") or "") + str(r.get("location") or "")
                            + str(r.get("device") or "")).strip(),
                    "address": str(r.get("bit") or "").strip()})
    return out


def _classify_added(added: list) -> tuple:
    """Node-aware split of added rows: a contiguous block of >=_UPGRADE_BLOCK = upgrade; an isolated row
    = forgotten signal (correction); a 2-3 row cluster = flagged for review. An upgrade carries the
    involved rows (desc / fld / address) for the retrofit detail."""
    by_node = defaultdict(list)
    for r in added:
        by_node[r.get("_node", "")].append(r)
    upgrades, forgotten, review = [], [], []
    for node, rows in by_node.items():
        rows.sort(key=lambda r: int(r.get("_row") or 0))
        if len(rows) >= _UPGRADE_BLOCK:
            upgrades.append({"node": node, "count": len(rows),
                             "desc": desc(rows[0]).replace("|", " ").strip(),
                             "rows": _added_detail(rows)})
        elif len(rows) == 1:
            forgotten.append(_row_brief(rows[0]))
        else:
            review.append({"node": node, "count": len(rows),
                           "desc": desc(rows[0]).replace("|", " ").strip()})
    return upgrades, forgotten, review


_CE_COMPARE = ["module", "address", "slot", "pin", "description", "type"]


def classify_ce(match_result: dict, old_areas: list, new_areas: list, weights: dict) -> dict:
    """Classify the C&E cause-row pairs. Address (c6) changes are COUNTED (grouped into one critical
    summary - never hidden), the other columns itemized per row. EFFECT columns are special - a lost
    effect (X->blank in an existing area) is a CRITICAL regression, a new effect column rolled across rows
    is an UPGRADE. Added cause rows that form a coherent contiguous block are an upgrade, else corrections."""
    pairs = match_result["pairs"]
    addr_changes = [(p["old"].get("address"), p["new"].get("address")) for p in pairs
                    if norm(p["old"].get("address")) != norm(p["new"].get("address"))]
    events = {}
    addr_event = detect_address_event(addr_changes)
    if addr_event:
        addr_event.update({"field": "address", "tier": "critical", "label": "C&E address re-map"})
        events["address"] = addr_event           # coordinated-re-map context only (never hides the rows)

    intact = changed = addr_rows = 0
    addr_tier = _tier(weights, "address")
    corrections: list = []
    by_tier = {"critical": 0, "major": 0, "minor": 0}
    by_direction = {"gap-fill": 0, "value-change": 0, "value-loss": 0}
    effects_lost: list = []          # an existing effect deleted (X -> blank) = critical regression
    new_area_cols = [a for a in new_areas if a not in old_areas]
    rollout_rows = 0

    for pair in pairs:
        old, new = pair["old"], pair["new"]
        old_eff, new_eff = old.get("effects", {}), new.get("effects", {})
        for area in old_areas:
            if norm(old_eff.get(area)) and not norm(new_eff.get(area)):
                effects_lost.append({"concat_id": old.get("concat_id"), "area": area,
                                     "desc": old.get("description"), "row": old.get("_row")})
        for area in new_area_cols:
            if norm(new_eff.get(area)) and not norm(old_eff.get(area)):
                rollout_rows += 1
        addr_changed = norm(old.get("address")) != norm(new.get("address"))
        if addr_changed:
            addr_rows += 1                        # the C&E address is grouped + counted, not itemized
        itemized = [f for f in _CE_COMPARE if f != "address" and norm(old.get(f)) != norm(new.get(f))]
        if not addr_changed and not itemized:
            intact += 1
            continue
        changed += 1
        tiers = ([addr_tier] if addr_changed else []) + [_tier(weights, f) for f in itemized]
        by_tier[_bucket(max(tiers, key=lambda t: TIER_RANK.get(t, 1)))] += 1
        if not itemized:
            continue                              # address-only -> counted in addr_rows + by_tier
        diffs = [{"field": f, "old": old.get(f, ""), "new": new.get(f, ""),
                  "tier": _tier(weights, f), "direction": _direction(old.get(f), new.get(f))}
                 for f in itemized]
        for d in diffs:
            by_direction[d["direction"]] += 1
        corrections.append({"concat_id": old.get("concat_id"), "desc": old.get("description"),
                            "row": old.get("_row"), "diffs": diffs,
                            "tier": max((d["tier"] for d in diffs), key=lambda t: TIER_RANK.get(t, 1)),
                            "directions": sorted({d["direction"] for d in diffs})})

    structural = ([{"field": "address", "label": "C&E address changes", "tier": addr_tier, "rows": addr_rows}]
                  if addr_rows else [])
    added = match_result["added"]
    added_is_upgrade = len(added) >= _UPGRADE_BLOCK and _contiguous(added)
    return {
        "matched": len(pairs), "intact": intact, "changed": changed,
        "corrections": corrections, "correction_count": len(corrections),
        "by_tier": by_tier, "by_direction": by_direction,
        "structural": structural, "structural_rows": addr_rows,
        "systematic_events": [_event_brief(e) for e in events.values()],
        "effects_lost": effects_lost,
        "new_area_columns": new_area_cols, "rollout_rows": rollout_rows,
        "added_total": len(added),
        "added_upgrade": {"count": len(added), "desc": (added[0].get("description") if added else "")}
        if added_is_upgrade else None,
        "added_corrections": [] if added_is_upgrade else [_ce_brief(r) for r in added],
        "removed": [_ce_brief(r) for r in match_result["removed"]],
    }


def _contiguous(rows: list) -> bool:
    nums = sorted(int(r.get("_row") or 0) for r in rows)
    return len(nums) >= 2 and (nums[-1] - nums[0]) <= len(nums) + 2


def _ce_brief(row: dict) -> dict:
    return {"concat_id": row.get("concat_id"), "desc": row.get("description"), "row": row.get("_row")}


_AREA_COMPARE = ["device_tag", "digital_output", "line_numbering", "description"]


def classify_area(match_result: dict, counts_old: dict, counts_new: dict, weights: dict) -> dict:
    """Classify the pooled AREA rows. Reports per-area row counts, how many matched rows MOVED to a
    different area sheet (the reorganization signal), the device-tag / address / line corrections, and a
    structural-reorganization flag. The digital_output address is netted as a systematic re-map."""
    pairs = match_result["pairs"]
    moved = sum(1 for p in pairs if p.get("moved"))
    addr_changes = [(p["old"].get("digital_output"), p["new"].get("digital_output")) for p in pairs
                    if norm(p["old"].get("digital_output")) != norm(p["new"].get("digital_output"))]
    addr_event = detect_address_event(addr_changes)
    events = {}
    if addr_event:
        addr_event.update({"field": "digital_output", "tier": "critical", "label": "AREA address re-map"})
        events["digital_output"] = addr_event

    corrections: list = []
    by_tier = {"critical": 0, "major": 0, "minor": 0}
    for pair in pairs:
        old, new = pair["old"], pair["new"]
        genuine = []
        for f in _AREA_COMPARE:
            if norm(old.get(f)) == norm(new.get(f)):
                continue
            ev = events.get(f)
            if ev and ev["member"](old.get(f), new.get(f)):
                continue
            genuine.append(f)
        if not genuine:
            continue
        diffs = [{"field": f, "old": old.get(f, ""), "new": new.get(f, ""),
                  "tier": _tier(weights, f), "direction": _direction(old.get(f), new.get(f))}
                 for f in genuine]
        row_tier = max((d["tier"] for d in diffs), key=lambda t: TIER_RANK.get(t, 1))
        corrections.append({"sheet_old": old.get("_sheet"), "sheet_new": new.get("_sheet"),
                            "moved": pair.get("moved"), "desc": old.get("description"),
                            "diffs": diffs, "tier": row_tier})
        by_tier[_bucket(row_tier)] += 1

    # a structural reorganization: a sheet that lost most of its rows OR many rows changed sheet.
    reorg = []
    for sheet in sorted(set(counts_old) | set(counts_new)):
        co, cn = counts_old.get(sheet, 0), counts_new.get(sheet, 0)
        if co and cn and abs(cn - co) >= max(8, co * 0.5):
            reorg.append({"sheet": sheet, "old": co, "new": cn})
        elif co and not cn:
            reorg.append({"sheet": sheet, "old": co, "new": 0})
        elif cn and not co:
            reorg.append({"sheet": sheet, "old": 0, "new": cn})
    return {
        "counts_old": counts_old, "counts_new": counts_new,
        "matched": len(pairs), "moved": moved,
        "corrections": corrections, "correction_count": len(corrections), "by_tier": by_tier,
        "systematic_events": [_event_brief(e) for e in events.values()],
        "removed": [{"sheet": r.get("_sheet"), "desc": r.get("description"),
                     "device_tag": r.get("device_tag")} for r in match_result["removed"]],
        "added": [{"sheet": r.get("_sheet"), "desc": r.get("description"),
                   "device_tag": r.get("device_tag")} for r in match_result["added"]],
        "reorganized": reorg,
    }


def _row_brief(row: dict) -> dict:
    return {"node": row.get("_node", ""), "sheet": row.get("_sheet"), "row": row.get("_row"),
            "fld": fld(row), "desc": desc(row).replace("|", " ").strip()}


def _event_brief(event: dict) -> dict:
    return {"field": event.get("field"), "label": event.get("label"), "kind": event["kind"],
            "rows": event["rows"], "tier": event.get("tier", "major"),
            "summary": event["summary"], "sample": event.get("sample", [])}
